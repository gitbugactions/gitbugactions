import datetime
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Set, Tuple

import dateutil.parser
import fire
import pygit2
import tqdm
from github import (
    GithubException,
    PaginatedList,
    PullRequest,
    Repository,
    UnknownObjectException,
)
from nltk.stem import PorterStemmer
from nltk.tokenize import wordpunct_tokenize
from unidiff import PatchSet

from gitbugactions.actions.action import Action
from gitbugactions.actions.actions import Act, ActCacheDirManager, ActTestsRun
from gitbugactions.actions.workflow import GitHubWorkflow
from gitbugactions.actions.workflow_factory import GitHubWorkflowFactory
from gitbugactions.collect_bugs.bug_patch import BugPatch
from gitbugactions.collect_bugs.collection_strategies import *
from gitbugactions.collect_bugs.test_config import TestConfig
from gitbugactions.github_api import GithubAPI
from gitbugactions.test_executor import TestExecutor
from gitbugactions.utils.actions_utils import get_default_github_actions
from gitbugactions.utils.file_reader import GitShowFileReader
from gitbugactions.utils.file_utils import FileType, get_file_type
from gitbugactions.utils.repo_utils import clone_repo, delete_repo_clone
from gitbugactions.utils.repo_state_manager import RepoStateManager
from gitbugactions.actions.templates.template_workflows import TemplateWorkflowManager


class PatchCollector:
    CLONE_SEM = threading.Semaphore(16)

    def __init__(self, repo: Repository, **kwargs):
        self.repo: Repository = repo
        self.language = repo.language.strip().lower()
        self.cloned = False
        self.clone_lock = threading.Lock()
        self.default_github_actions = None
        self.filter_on_commit_message = kwargs.get("filter_on_commit_message", True)
        self.filter_on_commit_time_start = kwargs.get(
            "filter_on_commit_time_start", None
        )
        self.filter_on_commit_time_end = kwargs.get("filter_on_commit_time_end", None)
        self.pull_requests = kwargs.get("pull_requests", False)
        self.filter_linked_to_pr = kwargs.get("filter_linked_to_pr", None)

    def __clone_repo(self):
        # Too many repos cloning at the same time lead to errors
        with PatchCollector.CLONE_SEM:
            with self.clone_lock:
                if self.cloned:
                    return
                self.delete_repo()
                repo_path = os.path.join(
                    tempfile.gettempdir(), self.repo.full_name.replace("/", "-")
                )
                repo_path = os.path.join(repo_path, str(uuid.uuid4()))
                logging.info(f"Cloning {self.repo.full_name} - {self.repo.clone_url}")
                self.repo_clone: pygit2.Repository = clone_repo(
                    self.repo.clone_url, repo_path
                )
                # Set gc.auto to 0 to avoid "too many open files" bug
                subprocess.run(
                    f"git config gc.auto 0",
                    cwd=repo_path,
                    shell=True,
                    capture_output=True,
                )
                self.first_commit = self.repo_clone.revparse_single(
                    str(self.repo_clone.head.target)
                )
                self.cloned = True

    def __is_bug_fix(self, commit: pygit2.Commit):
        tokens = wordpunct_tokenize(commit.message)
        stemmer = PorterStemmer()
        tokens = [stemmer.stem(token) for token in tokens]
        bug_fix_keywords = {"fix", "resolv", "patch", "repair", "correct", "workaround"}
        return any(keyword in tokens for keyword in bug_fix_keywords)

    def __get_patches(self, repo_clone, commit, previous_commit):
        diff = repo_clone.diff(str(previous_commit.id), str(commit.id))
        patch: PatchSet = PatchSet(diff.patch)
        bug_patch: PatchSet = PatchSet("")
        test_patch: PatchSet = PatchSet("")
        non_code_patch: PatchSet = PatchSet("")

        # FIXME change keywords according to build tool
        for p in patch:
            if (
                get_file_type(self.language, p.source_file) == FileType.TESTS
                or get_file_type(self.language, p.target_file) == FileType.TESTS
            ):
                test_patch.append(p)
            elif (
                get_file_type(self.language, p.source_file) == FileType.SOURCE
                or get_file_type(self.language, p.target_file) == FileType.SOURCE
            ):
                bug_patch.append(p)
            else:
                non_code_patch.append(p)

        return bug_patch, test_patch, non_code_patch

    def __test_patch(
        self,
        bug: BugPatch,
        act_cache_dir: str,
    ) -> List[Optional[List[ActTestsRun]]]:
        test_patch_runs = [None, None, None]
        self.__clone_repo()

        new_repo_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
        shutil.copytree(self.repo_clone.workdir, new_repo_path, symlinks=True)
        repo_clone = pygit2.Repository(os.path.join(new_repo_path, ".git"))

        try:
            executor = TestExecutor(
                repo_clone,
                self.language,
                act_cache_dir,
                self.default_github_actions,
            )

            def all_runs_crashed(x):
                return x is None or all(map(lambda act_run: act_run.failed, x))

            # Previous commit
            act_runs = bug.test_previous_commit(executor)
            if all_runs_crashed(act_runs):
                return test_patch_runs
            test_patch_runs[0] = act_runs

            # Previous commit with diff
            if len(bug.test_patch) > 0:
                act_runs = bug.test_previous_commit_with_diff(executor)
                if all_runs_crashed(act_runs):
                    return test_patch_runs
                test_patch_runs[1] = act_runs

            # Current commit
            act_runs = bug.test_current_commit(executor)
            if all_runs_crashed(act_runs):
                return test_patch_runs
            test_patch_runs[2] = act_runs
        finally:
            delete_repo_clone(repo_clone)

        return test_patch_runs

    def __get_related_commit_info(self, commit_hex: str):
        self.__clone_repo()

        commit = self.repo_clone.revparse_single(commit_hex)
        matches = re.findall("#[0-9]+", commit.message)
        issues = []

        if len(matches) > 0:
            github = GithubAPI()
            # We need to get the repo again to use the current token
            repo = github.get_repo(self.repo.full_name)
        else:
            return []

        for match in matches:
            match_id = int(match[1:])
            try:
                # GitHub's REST API considers every pull request an issue
                # https://docs.github.com/en/rest/issues/issues?apiVersion=2022-11-28#get-an-issue
                issue = repo.get_issue(match_id)
                is_pull_request = issue.pull_request is not None
                comments, labels, review_comments = [], [], None

                if is_pull_request:
                    review_comments = []
                    pull_request = issue.as_pull_request()
                    for comment in pull_request.get_review_comments():
                        review_comments.append(comment.body)

                for comment in issue.get_comments():
                    comments.append(comment.body)

                for label in issue.get_labels():
                    labels.append(
                        {"name": label.name, "description": label.description}
                    )

                issues.append(
                    {
                        "id": match_id,
                        "title": issue.title,
                        "body": issue.body,
                        "comments": comments,
                        "labels": labels,
                        "is_pull_request": is_pull_request,
                        "review_comments": review_comments,
                    }
                )
            except (UnknownObjectException, GithubException):
                continue

        return issues

    def __get_used_actions(self, commit: str) -> Set[Action]:
        """
        Get the actions used by the workflows declared in the commit version.
        Use git show to avoid checking out the whole version
        """
        actions: Set[Action] = set()
        reader = GitShowFileReader(commit, self.repo_clone.workdir)

        # Read workflows directory listing
        workflows_listing = reader.read_file(".github/workflows")
        if workflows_listing is None:
            return actions

        # Get the workflows paths
        workflow_paths = workflows_listing.split("\n")

        # Get the actions used by each workflow
        for workflow_path in workflow_paths:
            # Skip empty lines and non yaml files
            if workflow_path == "" or not (
                workflow_path.endswith(".yml") or workflow_path.endswith(".yaml")
            ):
                continue

            workflow_path = f".github/workflows/{workflow_path}"
            try:
                workflow: GitHubWorkflow = GitHubWorkflowFactory.create_workflow(
                    workflow_path, self.language, reader
                )
                actions.update(workflow.get_actions())
            except Exception:
                continue

        return actions

    def __get_template_actions(self) -> Set[Action]:
        """
        Get the actions used by the template workflow.
        """
        workflow_path = TemplateWorkflowManager.create_temp_workflow(
            self.repo_clone.workdir, self.language
        )
        if workflow_path is None:
            return set()
        try:
            workflow: GitHubWorkflow = GitHubWorkflowFactory.create_workflow(
                workflow_path, self.language
            )
            return workflow.get_actions()
        finally:
            TemplateWorkflowManager.remove_temp_workflow(workflow_path)

    def get_possible_patches(self):
        self.__clone_repo()
        if len(list(self.repo_clone.references.iterator())) == 0:
            return

        commit_to_patches: Dict[str, List[BugPatch]] = {}
        commits = list(self.repo_clone.walk(self.repo_clone.head.target))

        try:
            if self.pull_requests:
                pulls: PaginatedList[PullRequest] = self.repo.get_pulls()
                for pull in pulls:
                    pull_commits = pull.get_commits()
                    for pull_commit in pull_commits:
                        commits.append(self.repo_clone.get(pull_commit.sha))

            for commit in commits:
                if self.filter_on_commit_message and not self.__is_bug_fix(commit):
                    continue

                commit_time = datetime.datetime.fromtimestamp(
                    int(commit.commit_time), datetime.UTC
                )
                if (
                    self.filter_on_commit_time_start
                    and commit_time < self.filter_on_commit_time_start
                ):
                    continue

                if (
                    self.filter_on_commit_time_end
                    and commit_time > self.filter_on_commit_time_end
                ):
                    continue

                # Filter based on whether commit is linked to a PR
                if self.filter_linked_to_pr:
                    issues = self.__get_related_commit_info(str(commit.id))
                    has_pr = any(issue["is_pull_request"] for issue in issues)
                    if not has_pr:
                        continue

                try:
                    previous_commit = self.repo_clone.revparse_single(
                        str(commit.id) + "~1"
                    )
                except KeyError:
                    # The current commit is the first one
                    continue

                bug_patch, test_patch, non_code_patch = self.__get_patches(
                    self.repo_clone, commit, previous_commit
                )
                if len(bug_patch) == 0 and len(non_code_patch) == 0:
                    logging.info(
                        f"Skipping commit {self.repo.full_name} {str(commit.id)}: no bug patch"
                    )
                    continue

                actions: Set[Action] = set()
                actions.update(self.__get_used_actions(str(commit.id)))
                actions.update(self.__get_used_actions(str(previous_commit.id)))
                actions.update(self.__get_template_actions())

                if str(previous_commit.id) in commit_to_patches:
                    commit_to_patches[str(previous_commit.id)].append(
                        BugPatch(
                            self.repo,
                            commit,
                            previous_commit,
                            bug_patch,
                            test_patch,
                            non_code_patch,
                            actions,
                        )
                    )
                else:
                    commit_to_patches[str(previous_commit.id)] = [
                        BugPatch(
                            self.repo,
                            commit,
                            previous_commit,
                            bug_patch,
                            test_patch,
                            non_code_patch,
                            actions,
                        )
                    ]
                RepoStateManager.reset_to_commit(self.repo_clone, commit.id)
        finally:
            RepoStateManager.reset_to_commit(self.repo_clone, self.first_commit.id)

        # We remove the merges since when multiple bug patches point to the same
        # previous commit, merges tend to only add useless diffs to another commit
        # that already fixes the bug.
        # https://github.com/gitbugactions/gitbugactions/issues/40
        for previous_commit, grouped_patches in commit_to_patches.items():
            if len(grouped_patches) > 1:
                commit_to_patches[previous_commit] = list(
                    filter(
                        lambda patch: not patch.commit_message.startswith("Merge "),
                        grouped_patches,
                    )
                )

        patches: List[BugPatch] = sum(commit_to_patches.values(), [])
        patches.sort(key=lambda x: x.commit_timestamp)
        # Creates list without duplicates. Duplicates are patches with the same diff
        # We sort the list in order to keep the oldest patch
        patches = list(set(patches))
        # We sort again to return the patches in chronological order
        patches.sort(key=lambda x: x.commit_timestamp)
        return patches

    def set_default_github_actions(self):
        if not self.cloned:
            self.__clone_repo()
        self.default_github_actions = get_default_github_actions(
            self.repo_clone, self.first_commit, self.language
        )

    def test_patch(self, bug_patch: BugPatch):
        act_cache_dir = ActCacheDirManager.acquire_act_cache_dir()

        try:
            test_patch_runs = self.__test_patch(
                bug_patch,
                act_cache_dir,
            )
            bug_patch.actions_runs = test_patch_runs
            strategy = PatchCollector.check_runs(bug_patch)
            if strategy is None:
                return False
            else:
                bug_patch.strategy_used = strategy
                bug_patch.issues = self.__get_related_commit_info(bug_patch.commit)
                return True
        finally:
            ActCacheDirManager.return_act_cache_dir(act_cache_dir)

    @staticmethod
    def check_runs(bug_patch: BugPatch) -> Optional[str]:
        for strategy in TestConfig.strategies:
            if strategy.check(bug_patch):
                return strategy.name

        return None

    def delete_repo(self):
        if self.cloned:
            delete_repo_clone(self.repo_clone)
        self.cloned = False

    def analyze_specific_commits(self, commit_shas: List[str]) -> List[BugPatch]:
        """Analyze specific commits instead of scanning through all repository commits.

        Args:
            commit_shas (List[str]): List of commit SHAs to analyze

        Returns:
            List[BugPatch]: List of bug patches found in the specified commits
        """
        self.__clone_repo()
        if len(list(self.repo_clone.references.iterator())) == 0:
            return []

        bug_patches: List[BugPatch] = []

        try:
            for commit_sha in commit_shas:
                try:
                    # Get the commit and its parent
                    commit = self.repo_clone.revparse_single(commit_sha)

                    # Make sure the commit has a parent
                    if len(commit.parents) == 0:
                        logging.warning(f"Commit {commit_sha} has no parent, skipping")
                        continue

                    previous_commit = commit.parents[0]

                    # Get patches and actions
                    bug_patch, test_patch, non_code_patch = self.__get_patches(
                        self.repo_clone, commit, previous_commit
                    )

                    # Skip if there's no bug patch or non-code patch
                    if len(bug_patch) == 0 and len(non_code_patch) == 0:
                        logging.info(
                            f"Skipping commit {self.repo.full_name} {str(commit.id)}: no bug patch"
                        )
                        continue

                    # Get actions used in the commit and its parent
                    actions: Set[Action] = set()
                    actions.update(self.__get_used_actions(str(commit.id)))
                    actions.update(self.__get_used_actions(str(previous_commit.id)))
                    actions.update(self.__get_template_actions())

                    # Create a BugPatch object
                    patch = BugPatch(
                        self.repo,
                        commit,
                        previous_commit,
                        bug_patch,
                        test_patch,
                        non_code_patch,
                        actions,
                    )

                    bug_patches.append(patch)
                    RepoStateManager.reset_to_commit(self.repo_clone, commit.id)

                except Exception as e:
                    logging.error(f"Error analyzing commit {commit_sha}: {e}")
                    continue
        finally:
            # Reset to the original state
            RepoStateManager.reset_to_commit(self.repo_clone, self.first_commit.id)

        return bug_patches


def set_test_config(
    normalize_non_code_patch: bool = True,
    strategies: Tuple[str] = ("PASS_PASS", "FAIL_PASS"),
):
    TestConfig.normalize_non_code_patch = normalize_non_code_patch
    strategy_instances = [s() for s in CollectionStrategy.__subclasses__()]

    for strategy in strategies:
        TestConfig.strategies.append(
            next(
                filter(
                    lambda x: x.name == strategy,
                    strategy_instances,
                )
            )
        )


def parse_commit_url(commit_url: str) -> Tuple[str, str]:
    """Extract repository name and commit SHA from a GitHub commit URL.

    Args:
        commit_url (str): GitHub commit URL in the format "https://github.com/owner/repo/commit/sha"

    Returns:
        Tuple[str, str]: A tuple containing (repository_name, commit_sha)
    """
    parts = commit_url.strip().split("/")
    if len(parts) >= 5 and parts[2] == "github.com" and parts[5] == "commit":
        repo_name = f"{parts[3]}/{parts[4]}"
        commit_sha = parts[6]
        return repo_name, commit_sha
    raise ValueError(f"Invalid GitHub commit URL format: {commit_url}")


def collect_bugs(
    data_path: str,
    results_path="data/out_bugs",
    n_workers=1,
    memory_limit="7g",
    filter_on_commit_message: bool = True,
    filter_on_commit_time_start: str = None,
    filter_on_commit_time_end: str = None,
    normalize_non_code_patch: bool = True,
    strategies: Tuple[str] = ("PASS_PASS", "FAIL_PASS"),
    pull_requests: bool = False,
    filter_linked_to_pr: bool = None,
    base_image: str | None = None,
    use_default_actions: bool = False,
    commit_list_file: str = None,
):
    """Collects bug-fixes from the repos listed in `data_path`. The result is saved
    on `results_path`. A file `data.json` is also created with information about
    the repos.

    Args:
        data_path (str): Folder where the result of collect_repos is.
        results_path (str, optional): Folder on which the results will be saved.
                                      Defaults to "data/out_bugs".
        n_workers (int, optional): Number of parallel workers. Defaults to 1.
        memory_limit (str, optional): Memory limit per container (https://docs.docker.com/config/containers/resource_constraints/#limit-a-containers-access-to-memory).
                                      Defaults to "7g".
        filter_on_commit_message (bool, optional): If True, only commits with the word "fix" in the commit message will be considered.
        filter_on_commit_time_start (str, optional): If set, only commits after this date will be considered. The string must follow the format "yyyy-mm-dd HH:MM UTC".
        filter_on_commit_time_end (str, optional): If set, only commits before this date will be considered. The string must follow the format "yyyy-mm-dd HH:MM UTC".
        normalize_non_code_patch (bool, optional): If True, the non-code patch will be applied to previous commits. Defaults to True.
        strategies (Tuple[str], optional): List of strategies to be used. Defaults to ("PASS_PASS", "FAIL_PASS").
                                           The available strategies are: "PASS_PASS", "FAIL_PASS", "FAIL_FAIL", "FAIL_PASS_BUILD".
        pull_requests (bool, optional): If True, the commits in pull requests will be considered. Defaults to False.
        filter_linked_to_pr (bool, optional): If True, only include commits that are linked to pull requests. If False, only include commits that are not linked to pull requests. If None, include all commits. Defaults to None.
        base_image (str, optional): Base image to use for building the runner image. If None, uses default.
        use_default_actions (bool, optional): Whether to use and collect default GitHub actions from repositories. Defaults to False.
        commit_list_file (str, optional): Path to a JSON file containing a list of commit URLs to analyze. If provided, data_path is ignored. Defaults to None.
    """
    set_test_config(normalize_non_code_patch, strategies)

    Act.set_memory_limit(memory_limit)
    Act(base_image=base_image)  # Initialize Act with base_image
    github: GithubAPI = GithubAPI(
        per_page=100,
        pool_size=n_workers,
    )
    ActCacheDirManager.init_act_cache_dirs(n_dirs=n_workers)

    kwargs = {
        "filter_on_commit_message": filter_on_commit_message,
        "filter_on_commit_time_start": (
            dateutil.parser.parse(filter_on_commit_time_start)
            if filter_on_commit_time_start is not None
            else None
        ),
        "filter_on_commit_time_end": (
            dateutil.parser.parse(filter_on_commit_time_end)
            if filter_on_commit_time_end is not None
            else None
        ),
        "pull_requests": pull_requests,
        "filter_linked_to_pr": filter_linked_to_pr,
    }

    patch_collectors: List[Tuple[PatchCollector, Any]] = []

    # Create the results directory if it doesn't exist
    if not os.path.exists(results_path):
        os.makedirs(results_path)

    # Mode: analyze specific commits from a file
    if commit_list_file is not None and os.path.exists(commit_list_file):
        # Read and parse the commit list file
        with open(commit_list_file, "r") as f:
            commit_urls = json.load(f)

        # Group commits by repository to minimize cloning operations
        commits_by_repo = {}
        for commit_url in commit_urls:
            try:
                repo_name, commit_sha = parse_commit_url(commit_url)
                if repo_name not in commits_by_repo:
                    commits_by_repo[repo_name] = []
                commits_by_repo[repo_name].append(commit_sha)
            except ValueError as e:
                logging.error(f"Error parsing commit URL: {e}")
                continue

        logging.info(
            f"Found {len(commits_by_repo)} repositories with {len(commit_urls)} commits to analyze"
        )

        # Process each repository and its commits
        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            future_to_collector: Dict[Future, Tuple[PatchCollector, List[str]]] = {}

            for repo_name, commit_shas in commits_by_repo.items():
                try:
                    repo = github.get_repo(repo_name)
                    patch_collector = PatchCollector(repo, **kwargs)
                    future_to_collector[
                        executor.submit(
                            patch_collector.analyze_specific_commits, commit_shas
                        )
                    ] = (patch_collector, commit_shas)
                except Exception as e:
                    logging.error(f"Error getting repository {repo_name}: {e}")
                    continue

            for future in tqdm.tqdm(
                as_completed(future_to_collector), total=len(future_to_collector)
            ):
                try:
                    patch_collector, _ = future_to_collector[future]
                    result = future.result()
                except Exception:
                    logging.error(
                        f"Error while collecting commits from {patch_collector.repo}: {traceback.format_exc()}"
                    )
                else:
                    patch_collectors.append((patch_collector, result))

    # Default mode: analyze repositories based on data_path
    else:
        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            future_to_collector: Dict[Future, PatchCollector] = {}

            dir_list = os.listdir(data_path)
            for file in dir_list:
                if file.endswith(".json"):
                    with open(os.path.join(data_path, file), "r") as f:
                        run = json.loads(f.read())

                        if (
                            (
                                run["number_of_test_actions"] == 1
                                or run["using_template_workflow"]
                            )
                            and "actions_run" in run
                            and len(run["actions_run"]["tests"]) > 0
                        ):
                            repo = github.get_repo(run["repository"])
                            patch_collector = PatchCollector(repo, **kwargs)
                            future_to_collector[
                                executor.submit(patch_collector.get_possible_patches)
                            ] = patch_collector

            for future in tqdm.tqdm(
                as_completed(future_to_collector), total=len(future_to_collector)
            ):
                try:
                    patch_collector = future_to_collector[future]
                    result = future.result()
                except Exception:
                    logging.error(
                        f"Error while collecting commits from {patch_collector.repo}: {traceback.format_exc()}"
                    )
                else:
                    patch_collectors.append((patch_collector, result))

    data_path = os.path.join(results_path, "data.json")
    repos = {}
    with open(data_path, "w") as fp:
        for patch_collector, bug_patches in patch_collectors:
            repos[patch_collector.repo.full_name] = {
                "clone_url": patch_collector.repo.clone_url,
                "commits": patch_collector.repo.get_commits().totalCount,
                "possible_bug_patches": len(bug_patches),
                "stars": patch_collector.repo.stargazers_count,
                "size": patch_collector.repo.size,
            }
        fp.write(json.dumps(repos))

    # Populate the base cache dir with required actions
    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures_to_actions: Dict[Future, Action] = {}
        actions_to_download: Set[Action] = set()
        for patch_collector, bug_patches in patch_collectors:
            for bug_patch in bug_patches:
                actions_to_download.update(bug_patch.actions)

        for action in actions_to_download:
            futures_to_actions[
                executor.submit(ActCacheDirManager.cache_action, action)
            ] = action

        for future in tqdm.tqdm(
            as_completed(futures_to_actions), total=len(futures_to_actions)
        ):
            try:
                future.result()
            except Exception:
                logging.error(
                    f"Error while downloading action: {traceback.format_exc()}"
                )
                continue

    # Only collect default GitHub actions if specified
    if use_default_actions:
        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            future_to_collector: Dict[Future, PatchCollector] = {}
            for patch_collector, _ in patch_collectors:
                future_to_collector[
                    executor.submit(patch_collector.set_default_github_actions)
                ] = patch_collector

            for future in tqdm.tqdm(
                as_completed(future_to_collector), total=len(future_to_collector)
            ):
                try:
                    patch_collector = future_to_collector[future]
                    future.result()
                except Exception:
                    logging.error(
                        f"Error while setting default github actions from {patch_collector.repo}: {traceback.format_exc()}"
                    )
                    continue
    else:
        logging.info(
            "Skipping collection of default GitHub actions as requested by use_default_actions=False"
        )

    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        future_to_patches: Dict[Future, Tuple[BugPatch]] = {}
        for patch_collector, bug_patches in patch_collectors:
            for bug_patch in bug_patches:
                future_to_patches[
                    executor.submit(patch_collector.test_patch, bug_patch)
                ] = bug_patch

        for future in tqdm.tqdm(
            as_completed(future_to_patches), total=len(future_to_patches)
        ):
            try:
                bug_patch = future_to_patches[future]
                is_patch = future.result()
            except Exception:
                logging.error(
                    f"Error while collecting patches from {bug_patch.repo}: {traceback.format_exc()}"
                )
            else:
                if is_patch:
                    data_path = os.path.join(
                        results_path,
                        bug_patch.repo.full_name.replace("/", "-") + ".json",
                    )
                    with open(data_path, "a") as fp:
                        data = bug_patch.get_data()
                        fp.write((json.dumps(data) + "\n"))

    for patch_collector, _ in patch_collectors:
        patch_collector.delete_repo()


def main():
    fire.Fire(collect_bugs)


if __name__ == "__main__":
    sys.exit(main())

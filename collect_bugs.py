import os, sys, re, subprocess, traceback
import uuid, json
import shutil
import pygit2
import tempfile
import logging
import tqdm
import threading
import fire
from nltk.tokenize import wordpunct_tokenize
from nltk.stem import PorterStemmer
from typing import List, Tuple, Any, Dict, Set
from enum import Enum
from datetime import datetime
from github import Github, Repository, UnknownObjectException, GithubException
from unidiff import PatchSet
from crawlergpt.util import delete_repo_clone
from crawlergpt.actions.actions import (
    ActTestsRun,
    ActCacheDirManager,
    Act,
)
from crawlergpt.actions.workflow import GitHubWorkflow, GitHubWorkflowFactory
from crawlergpt.actions.action import Action
from crawlergpt.test_executor import TestExecutor
from crawlergpt.github_token import GithubToken
from crawlergpt.util import (
    get_default_github_actions,
    clone_repo,
    get_file_type,
    FileType,
)
from concurrent.futures import ThreadPoolExecutor, Future, as_completed


class CollectionStrategy(Enum):
    UNKNOWN = 0
    PASS_PASS = 1
    FAIL_PASS = 2


class BugPatch:
    def __init__(
        self,
        repo: Repository,
        commit: pygit2.Commit,
        previous_commit: pygit2.Commit,
        bug_patch: PatchSet,
        test_patch: PatchSet,
        non_code_patch: PatchSet,
        actions: Set[Action],
    ):
        self.repo: Repository = repo
        self.language: str = repo.language.lower().strip()
        self.commit: str = commit.hex
        self.commit_message: str = commit.message
        self.commit_timestamp: str = (
            datetime.utcfromtimestamp(int(commit.commit_time)).isoformat() + "Z"
        )
        self.previous_commit: str = previous_commit.hex
        self.previous_commit_message: str = previous_commit.message
        self.previous_commit_timestamp: str = (
            datetime.utcfromtimestamp(int(previous_commit.commit_time)).isoformat()
            + "Z"
        )
        self.time_to_patch: str = str(
            datetime.utcfromtimestamp(int(commit.commit_time))
            - datetime.utcfromtimestamp(int(previous_commit.commit_time))
        )
        self.bug_patch: PatchSet = bug_patch
        self.test_patch: PatchSet = test_patch
        self.non_code_patch: PatchSet = non_code_patch
        self.actions: Set[Action] = actions
        self.strategy_used: CollectionStrategy = CollectionStrategy.UNKNOWN
        self.issues = None
        # The actions are grouped by each phase of the strategy used
        self.actions_runs: List[List[ActTestsRun]] = []

    def get_data(self):
        actions_runs = []

        for runs in self.actions_runs:
            if runs is None:
                actions_runs.append(None)
                continue
            runs_data = []

            for run in runs:
                runs_data.append(run.asdict())
            actions_runs.append(runs_data)

        return {
            "repository": self.repo.full_name,
            "language": self.language,
            "clone_url": self.repo.clone_url,
            "collection_timestamp": datetime.utcnow().isoformat() + "Z",
            "commit_hash": self.commit,
            "commit_message": self.commit_message,
            "commit_timestamp": self.commit_timestamp,
            "previous_commit_hash": self.previous_commit,
            "previous_commit_message": self.previous_commit_message,
            "previous_commit_timestamp": self.previous_commit_timestamp,
            "time_to_patch": self.time_to_patch,
            "bug_patch": str(self.bug_patch),
            "test_patch": str(self.test_patch),
            "non_code_patch": str(self.non_code_patch),
            "actions_runs": actions_runs,
            "strategy": self.strategy_used.name,
            "issues": self.issues,
        }

    def __remove_patch_index(self, patch: PatchSet) -> str:
        lines = str(patch).split("\n")
        return "\n".join(list(filter(lambda line: not line.startswith("index"), lines)))

    def __hash__(self):
        return hash(
            (
                self.__remove_patch_index(self.bug_patch),
                self.__remove_patch_index(self.test_patch),
                self.__remove_patch_index(self.non_code_patch),
            )
        )

    def __eq__(self, __value: object) -> bool:
        if not isinstance(__value, BugPatch):
            return False
        return (
            self.__remove_patch_index(self.bug_patch)
            == self.__remove_patch_index(__value.bug_patch)
            and self.__remove_patch_index(self.test_patch)
            == self.__remove_patch_index(__value.test_patch)
            and self.__remove_patch_index(self.non_code_patch)
            == self.__remove_patch_index(__value.non_code_patch)
        )

    def __ne__(self, __value: object) -> bool:
        return not self.__eq__(__value)


class PatchCollector:
    CLONE_SEM = threading.Semaphore(16)

    def __init__(self, repo: Repository):
        self.repo: Repository = repo
        self.language = repo.language.strip().lower()
        self.cloned = False
        self.clone_lock = threading.Lock()

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
                self.cloned = True

    def __is_bug_fix(self, commit: pygit2.Commit):
        tokens = wordpunct_tokenize(commit.message)
        stemmer = PorterStemmer()
        tokens = [stemmer.stem(token) for token in tokens]
        return "fix" in tokens

    def __get_patches(self, repo_clone, commit, previous_commit):
        diff = repo_clone.diff(previous_commit.hex, commit.hex)
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

    def __cleanup_repo(
        self, repo_clone: pygit2.Repository, repo_path: str, commit: pygit2.Commit
    ):
        """
        Cleanups up repository dir for any untracked or modified files
        """
        repo_clone.reset(commit.oid, pygit2.GIT_RESET_HARD)
        subprocess.run(["git", "clean", "-f", "-d"], cwd=repo_path, capture_output=True)

    def __test_patch(
        self, commit_hex, previous_commit_hex, test_patch, non_code_patch, act_cache_dir
    ):
        test_patch_runs = [None, None, None]
        self.__clone_repo()

        new_repo_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
        shutil.copytree(self.repo_clone.workdir, new_repo_path)
        repo_clone = pygit2.Repository(os.path.join(new_repo_path, ".git"))

        try:
            executor = TestExecutor(
                repo_clone,
                self.language,
                act_cache_dir,
                self.default_github_actions,
            )
            first_commit = repo_clone.revparse_single(self.first_commit.hex)
            repo_clone.reset(first_commit.oid, pygit2.GIT_RESET_HARD)
            commit = repo_clone.revparse_single(commit_hex)
            previous_commit = repo_clone.revparse_single(previous_commit_hex)
            all_runs_crashed = lambda x: all(map(lambda act_run: act_run.failed, x))

            # Previous commit
            repo_clone.checkout_tree(previous_commit)
            # Creates ref to avoid "failed to identify reference"
            repo_clone.create_tag(
                str(uuid.uuid4()),
                previous_commit.oid,
                pygit2.GIT_OBJ_COMMIT,
                previous_commit.author,
                previous_commit.message,
            )
            repo_clone.set_head(previous_commit.oid)

            if len(non_code_patch) > 0:
                try:
                    repo_clone.apply(pygit2.Diff.parse_diff(str(non_code_patch)))
                except pygit2.GitError:
                    # Invalid patches
                    return test_patch_runs
            act_runs = executor.run_tests()
            if all_runs_crashed(act_runs):
                return test_patch_runs
            test_patch_runs[0] = act_runs

            self.__cleanup_repo(repo_clone, new_repo_path, previous_commit)

            if len(test_patch) > 0:
                # Apply diff and run tests
                try:
                    repo_clone.apply(pygit2.Diff.parse_diff(str(test_patch)))
                    if len(non_code_patch) > 0:
                        repo_clone.apply(pygit2.Diff.parse_diff(str(non_code_patch)))
                except pygit2.GitError:
                    # Invalid patches
                    return test_patch_runs
                act_runs = executor.run_tests()
                if all_runs_crashed(act_runs):
                    return test_patch_runs
                test_patch_runs[1] = act_runs

                self.__cleanup_repo(repo_clone, new_repo_path, previous_commit)

            # Current commit
            repo_clone.checkout_tree(commit)
            self.__cleanup_repo(repo_clone, new_repo_path, commit)

            # Creates ref to avoid "failed to identify reference"
            repo_clone.create_tag(
                str(uuid.uuid4()),
                commit.oid,
                pygit2.GIT_OBJ_COMMIT,
                commit.author,
                commit.message,
            )
            repo_clone.set_head(commit.oid)
            act_runs = executor.run_tests()
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
            token = GithubToken.get_token()
            # We need to get the repo again to use the current token
            repo = token.github.get_repo(self.repo.full_name)
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

        # Search for workflows in the commit version
        run = subprocess.run(
            f"git show {commit}:.github/workflows",
            cwd=self.repo_clone.workdir,
            shell=True,
            capture_output=True,
        )

        # If the folder does not exist, there are no workflows
        if run.returncode != 0:
            return actions

        # Get the workflows paths
        workflow_paths = run.stdout.decode("utf-8").split("\n")

        # Get the actions used by each workflow
        for workflow_path in workflow_paths:
            # Skip empty lines and non yaml files
            if workflow_path == "" or not (
                workflow_path.endswith(".yml") or workflow_path.endswith(".yaml")
            ):
                continue

            # Read the workflow file
            run = subprocess.run(
                f"git show {commit}:.github/workflows/{workflow_path}",
                cwd=self.repo_clone.workdir,
                shell=True,
                capture_output=True,
            )
            if run.returncode != 0:
                continue

            # Get the actions used by the workflow
            try:
                workflow: GitHubWorkflow = GitHubWorkflowFactory.create_workflow(
                    "", self.language, content=run.stdout.decode("utf-8")
                )
                actions.update(workflow.get_actions())
            except Exception:
                continue

        return actions

    def get_possible_patches(self):
        self.__clone_repo()
        if len(list(self.repo_clone.references.iterator())) == 0:
            return

        self.first_commit = self.repo_clone.revparse_single(
            str(self.repo_clone.head.target)
        )
        self.default_github_actions = get_default_github_actions(
            self.repo_clone, self.first_commit, self.language
        )

        commit_to_patches: Dict[str, List[BugPatch]] = {}
        try:
            for commit in self.repo_clone.walk(self.repo_clone.head.target):
                if not self.__is_bug_fix(commit):
                    continue

                try:
                    previous_commit = self.repo_clone.revparse_single(commit.hex + "~1")
                except KeyError:
                    # The current commit is the first one
                    continue

                bug_patch, test_patch, non_code_patch = self.__get_patches(
                    self.repo_clone, commit, previous_commit
                )
                if len(bug_patch) == 0:
                    logging.info(
                        f"Skipping commit {self.repo.full_name} {commit.hex}: no bug patch"
                    )
                    continue

                actions: Set[Action] = set()
                actions.update(self.__get_used_actions(commit.oid.hex))
                actions.update(self.__get_used_actions(previous_commit.oid.hex))

                if previous_commit.hex in commit_to_patches:
                    commit_to_patches[previous_commit.hex].append(
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
                    commit_to_patches[previous_commit.hex] = [
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
                self.__cleanup_repo(
                    self.repo_clone, self.repo_clone.workdir, self.first_commit
                )
        finally:
            self.repo_clone.reset(self.first_commit.oid, pygit2.GIT_RESET_HARD)

        # We remove the merges since when multiple bug patches point to the same
        # previous commit, merges tend to only add useless diffs to another commit
        # that already fixes the bug.
        # https://github.com/Nfsaavedra/crawlergpt/issues/40
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

    def __check_tests_were_fixed(
        self, run_failed: List[ActTestsRun], run_passed: List[ActTestsRun]
    ):
        flat_failed_tests = sum(
            map(lambda act_run: act_run.failed_tests, run_failed), []
        )
        flat_tests = sum(map(lambda act_run: act_run.tests, run_passed), [])

        for failed_test in flat_failed_tests:
            for test in flat_tests:
                if (
                    failed_test.classname == test.classname
                    and failed_test.name == test.name
                    and test.is_passed
                ):
                    break
            else:
                return False
        return True

    def test_patch(self, bug_patch: BugPatch):
        def flat_failed_tests(runs):
            return sum(map(lambda act_run: act_run.failed_tests, runs), [])

        act_cache_dir = ActCacheDirManager.acquire_act_cache_dir()

        try:
            test_patch_runs = self.__test_patch(
                bug_patch.commit,
                bug_patch.previous_commit,
                bug_patch.test_patch,
                bug_patch.non_code_patch,
                act_cache_dir=act_cache_dir,
            )
            bug_patch.actions_runs = test_patch_runs

            prev_commit_passed = (
                bug_patch.actions_runs[0] is not None
                and len(flat_failed_tests(bug_patch.actions_runs[0])) == 0
            )
            prev_with_diff_failed = (
                bug_patch.actions_runs[1] is not None
                and len(flat_failed_tests(bug_patch.actions_runs[1])) > 0
            )
            curr_commit_passed = (
                bug_patch.actions_runs[2] is not None
                and len(flat_failed_tests(bug_patch.actions_runs[2])) == 0
            )

            # PASS_PASS strategy
            if (
                # previous commit passed
                prev_commit_passed
                # previous commit with new tests failed
                and prev_with_diff_failed
                # current commit passed
                and curr_commit_passed
                # test patch is not empty
                and len(bug_patch.test_patch) > 0
                # test patch is not removals only
                and not (
                    bug_patch.test_patch.removed > 0 and bug_patch.test_patch.added == 0
                )
                # check if tests from previous commit w/diff were fixed
                and self.__check_tests_were_fixed(
                    bug_patch.actions_runs[1], bug_patch.actions_runs[2]
                )
            ):
                bug_patch.strategy_used = CollectionStrategy.PASS_PASS
                bug_patch.issues = self.__get_related_commit_info(bug_patch.commit)
                return True

            prev_commit_failed = (
                bug_patch.actions_runs[0] is not None
                and len(flat_failed_tests(bug_patch.actions_runs[0])) > 0
            )

            # FAIL_PASS strategy
            if (
                # previous commit failed
                prev_commit_failed
                # no changes have been made in the tests
                and len(bug_patch.test_patch) == 0
                # current commit passed
                and curr_commit_passed
                # check if tests from previous commit were fixed
                and self.__check_tests_were_fixed(
                    bug_patch.actions_runs[0], bug_patch.actions_runs[2]
                )
            ):
                bug_patch.strategy_used = CollectionStrategy.FAIL_PASS
                bug_patch.issues = self.__get_related_commit_info(bug_patch.commit)
                return True

            return False

        finally:
            ActCacheDirManager.return_act_cache_dir(act_cache_dir)

    def delete_repo(self):
        if self.cloned:
            delete_repo_clone(self.repo_clone)
        self.cloned = False


def collect_bugs(
    data_path: str, results_path="data/out_bugs", n_workers=1, memory_limit="7g"
):
    """Collects bugs from the repos listed in `data_path`. The result is saved
    on `results_path`. A file `data.json` is also created with information about
    the repos.

    Args:
        data_path (str): Folder where the result of collect_repos is.
        results_path (str, optional): Folder on which the results will be saved.
                                      Defaults to "data/out_bugs".
        n_workers (int, optional): Number of parallel workers. Defaults to 1.
        memory_limit (str, optional): Memory limit per container (https://docs.docker.com/config/containers/resource_constraints/#limit-a-containers-access-to-memory).
                                      Defaults to '7g'.
    """
    Act.set_memory_limit(memory_limit)
    token = GithubToken.get_token()
    github: Github = Github(
        login_or_token=token if token is None else token.token,
        per_page=100,
        pool_size=n_workers,
    )
    ActCacheDirManager.init_act_cache_dirs(n_dirs=n_workers)

    patch_collectors: List[Tuple[PatchCollector, Any]] = []
    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        future_to_collector: Dict[Future, PatchCollector] = {}

        dir_list = os.listdir(data_path)
        for file in dir_list:
            if file.endswith(".json"):
                with open(os.path.join(data_path, file), "r") as f:
                    run = json.loads(f.read())
                    if not os.path.exists(results_path):
                        os.mkdir(results_path)

                    if (
                        run["number_of_test_actions"] == 1
                        and "actions_run" in run
                        and len(run["actions_run"]["tests"]) > 0
                    ):
                        repo = github.get_repo(run["repository"])
                        patch_collector = PatchCollector(repo)
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
                    f"Error wile collecting patches from {bug_patch.repo}: {traceback.format_exc()}"
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

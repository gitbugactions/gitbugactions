import os, sys, re
import uuid, json
import shutil
import pygit2
import tempfile
import logging
import copy
import threading
import fire
from typing import List
from enum import Enum
from datetime import datetime
from github import Github, Repository, UnknownObjectException, GithubException
from unidiff import PatchSet
from dataclasses import asdict
from crawlergpt.util import delete_repo_clone
from crawlergpt.actions.actions import GitHubActions, ActTestsRun
from crawlergpt.github_token import GithubToken
from concurrent.futures import ThreadPoolExecutor

class CollectionStrategy(Enum):
    UNKNOWN = 0
    PASS_PASS = 1
    FAIL_PASS = 2

class BugPatch:
    def __init__(self, repo, commit, previous_commit, bug_patch, test_patch):
        self.repo: Repository = repo
        self.commit: str = commit.hex
        self.commit_message: str = commit.message
        unix_timestamp = int(commit.commit_time)
        self.commit_timestamp: str = datetime.utcfromtimestamp(unix_timestamp).isoformat() + "Z"
        self.previous_commit: str = previous_commit.hex
        self.bug_patch: PatchSet = bug_patch
        self.test_patch: PatchSet = test_patch
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
                run_data = asdict(run)
                run_data['tests'] = []
                for test in run.tests:
                    results = []
                    for result in test.result:
                        results.append({
                            'result': result.__class__.__name__,
                            'message': result.message,
                            'type': result.type
                        })
                    if len(results) == 0:
                        results.append({ 'result': 'Passed', 'message': '', 'type': '' })

                    run_data['tests'].append({
                        'classname': test.classname,
                        'name': test.name,
                        'time': test.time,
                        'results': results,
                        'stdout': test.system_out,
                        'stderr': test.system_err
                    })
                runs_data.append(run_data)
            actions_runs.append(runs_data)

        return { 
            'repository': self.repo.full_name,
            'stars': self.repo.stargazers_count,
            'language': self.repo.language.strip().lower(),
            'size': self.repo.size,
            'clone_url': self.repo.clone_url,
            'collection_timestamp': datetime.utcnow().isoformat() + "Z",
            'commit_hash': self.commit,
            'commit_message': self.commit_message,
            'commit_timestamp': self.commit_timestamp,
            'bug_patch': str(self.bug_patch),
            'test_patch': str(self.test_patch),
            'actions_runs': actions_runs,
            'strategy': self.strategy_used.name,
            'issues': self.issues
        }


class PatchCollector:
    def __init__(self, repo: Repository):
        self.repo: Repository = repo
        self.language = repo.language.strip().lower()
        self.cloned = False
        self.clone_lock = threading.Lock()

    def __clone_repo(self):
        self.clone_lock.acquire()
        if self.cloned:
            self.clone_lock.release()
            return
        self.delete_repo()
        self.repo_path = os.path.join(tempfile.gettempdir(), self.repo.full_name.replace('/', '-'))
        self.repo_path = os.path.join(self.repo_path, str(uuid.uuid4()))
        logging.info(f"Cloning {self.repo.full_name} - {self.repo.clone_url}")
        self.repo_clone: pygit2.Repository = pygit2.clone_repository(
            self.repo.clone_url, 
            self.repo_path
        )
        self.cloned = True
        self.__get_default_actions()
        self.clone_lock.release()

    def __get_default_actions(self):
        if len(list(self.repo_clone.references.iterator())) == 0:
            return
        self.first_commit = None

        for commit in self.repo_clone.walk(self.repo_clone.head.target):
            if self.first_commit is None:
                self.first_commit = commit
            self.repo_clone.checkout_tree(commit)
            self.repo_clone.set_head(commit.oid)
            actions = GitHubActions(self.repo_path, self.language)
            if len(actions.test_workflows) > 0:
                self.default_actions = actions

        self.repo_clone.reset(self.first_commit.oid, pygit2.GIT_RESET_HARD)
        
    def __is_bug_fix(self, commit):
        return 'fix' in commit.message.lower()
    
    def __get_patches(self, repo_clone, commit, previous_commit):
        diff = repo_clone.diff(previous_commit.hex, commit.hex)
        patch = PatchSet(diff.patch)
        bug_patch = PatchSet('')
        test_patch = PatchSet('')

        for p in patch:
            # FIXME change keywords according to build tool
            if any([keyword in p.source_file.split(os.sep) for keyword in ['test', 'tests']]):
                test_patch.append(p)
            else:
                bug_patch.append(p)

        return bug_patch, test_patch
    
    def __run_tests(self, repo_clone) -> List[ActTestsRun]:
        act_runs = []

        test_actions = GitHubActions(repo_clone.workdir, self.language)
        if len(test_actions.test_workflows) == 0:
            for workflow in self.default_actions.test_workflows:
                new_workflow = copy.deepcopy(workflow)
                new_workflow.path = os.path.join(repo_clone.workdir, 
                    '.github/workflows', os.path.basename(workflow.path))
                test_actions.test_workflows.append(new_workflow)
        # Act creates names for the containers by hashing the content of the workflows
        # To avoid conflicts between threads, we randomize the name
        for workflow in test_actions.test_workflows:
            workflow.doc["name"] = str(uuid.uuid4())
        test_actions.save_workflows()

        for workflow in test_actions.test_workflows:
            act_runs.append(test_actions.run_workflow(workflow))

        test_actions.delete_workflows()

        return act_runs
    
    def __test_patch(self, commit_hex, previous_commit_hex, test_patch):
        test_patch_runs = [None, None, None]
        if not self.cloned:
            self.__clone_repo()

        new_repo_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
        shutil.copytree(self.repo_path, new_repo_path)

        repo_clone = pygit2.Repository(os.path.join(new_repo_path, ".git"))
        try:
            first_commit = repo_clone.revparse_single(self.first_commit.hex)
            repo_clone.reset(first_commit.oid, pygit2.GIT_RESET_HARD)
            commit = repo_clone.revparse_single(commit_hex)
            previous_commit = repo_clone.revparse_single(previous_commit_hex)

            # Previous commit
            repo_clone.checkout_tree(previous_commit)
            # Creates ref to avoid "failed to identify reference"
            repo_clone.create_tag(str(uuid.uuid4()), previous_commit.oid, pygit2.GIT_OBJ_COMMIT, previous_commit.author, previous_commit.message)
            repo_clone.set_head(previous_commit.oid)
            
            act_runs = self.__run_tests(repo_clone)
            all_runs_failed = all(map(lambda act_run: act_run.failed, act_runs))
            if all_runs_failed:
                return test_patch_runs
            test_patch_runs[0] = act_runs

            if len(test_patch) > 0:
                # Apply diff and run tests
                try:
                    repo_clone.apply(pygit2.Diff.parse_diff(str(test_patch)))
                except pygit2.GitError:
                    # Invalid patches
                    return test_patch_runs
                act_runs = self.__run_tests(repo_clone)
                if all_runs_failed:
                    return test_patch_runs
                test_patch_runs[1] = act_runs

            # Current commit
            repo_clone.checkout_tree(commit)
            # Creates ref to avoid "failed to identify reference"
            repo_clone.create_tag(str(uuid.uuid4()), commit.oid, pygit2.GIT_OBJ_COMMIT, \
                                    commit.author, commit.message)
            repo_clone.set_head(commit.oid)
            act_runs = self.__run_tests(repo_clone)
            all_runs_failed = all(map(lambda act_run: act_run.failed, act_runs))
            if all_runs_failed:
                return test_patch_runs
            test_patch_runs[2] = act_runs
        finally:
            delete_repo_clone(repo_clone)

        return test_patch_runs
    

    def __get_related_commit_info(self, commit_hex: str):
        if not self.cloned:
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
                    labels.append({'name': label.name, 'description': label.description})

                issues.append({
                    'id': match_id,
                    'title': issue.title,
                    'body': issue.body,
                    'comments': comments,
                    'labels': labels,
                    'is_pull_request': is_pull_request,
                    'review_comments': review_comments
                })
            except (UnknownObjectException, GithubException):
                continue

        return issues
    
    def get_possible_patches(self):
        if not self.cloned:
            self.__clone_repo()
        if len(list(self.repo_clone.references.iterator())) == 0:
            return

        patches = []
        first_commit = None

        for commit in self.repo_clone.walk(self.repo_clone.head.target):
            if first_commit is None:
                first_commit = commit

            if not self.__is_bug_fix(commit):
                continue

            try:
                previous_commit = self.repo_clone.revparse_single(commit.hex + '~1')
            except KeyError:
                # The current commit is the first one
                continue

            bug_patch, test_patch = self.__get_patches(self.repo_clone, commit, previous_commit)
            if len(bug_patch) == 0:
                logging.info(f"Skipping commit {self.repo.full_name} {commit.hex}: no bug patch")
                continue

            patches.append(BugPatch(self.repo, commit, previous_commit, bug_patch, test_patch))
        
        return patches

    def test_patch(self, bug_patch: BugPatch, delete_repo = False):
        def flat_failed_tests(runs):
            return sum(map(lambda act_run: act_run.failed_tests, runs), [])
        
        test_patch_runs = self.__test_patch(bug_patch.commit, 
                                            bug_patch.previous_commit, 
                                            bug_patch.test_patch)
        bug_patch.actions_runs = test_patch_runs
        if delete_repo:
            self.delete_repo()
        
        prev_commit_passed = (bug_patch.actions_runs[0] is not None and 
                                 len(flat_failed_tests(bug_patch.actions_runs[0])) == 0)
        prev_with_diff_failed = (bug_patch.actions_runs[1] is not None and 
                                 len(flat_failed_tests(bug_patch.actions_runs[1])) > 0)
        curr_commit_passed = (bug_patch.actions_runs[2] is not None and 
                                 len(flat_failed_tests(bug_patch.actions_runs[2])) == 0)
        
        # PASS_PASS strategy
        if prev_commit_passed and prev_with_diff_failed and curr_commit_passed:
            bug_patch.strategy_used = CollectionStrategy.PASS_PASS
            bug_patch.issues = self.__get_related_commit_info(bug_patch.commit)
            return True

        prev_commit_failed = (bug_patch.actions_runs[0] is not None and 
                                 len(flat_failed_tests(bug_patch.actions_runs[0])) > 0)
        
        # FAIL_PASS strategy
        if prev_commit_failed and curr_commit_passed:
            bug_patch.strategy_used = CollectionStrategy.FAIL_PASS
            bug_patch.issues = self.__get_related_commit_info(bug_patch.commit)
            return True

        return False
    
    def delete_repo(self):
        if hasattr(self, "repo_path"):
            delete_repo_clone(self.repo_clone)
        self.cloned = False


def collect_bugs(data_path, results_path="data/out_bugs", n_workers=1):
    token = GithubToken.get_token()
    github: Github = Github(
        login_or_token=token if token is None else token.token, 
        per_page=100, 
    )

    executor = ThreadPoolExecutor(max_workers=n_workers)
    collectors_futures = []
    patch_collectors = []

    dir_list = os.listdir(data_path)
    for file in dir_list:
        with open(os.path.join(data_path, file), "r") as f:
            run = json.loads(f.read())
            if not os.path.exists(results_path):
                os.mkdir(results_path)

            if run["actions_successful"] and run["number_of_test_actions"] == 1:
                repo = github.get_repo(run["repository"])
                patch_collector = PatchCollector(repo)
                future = executor.submit(patch_collector.get_possible_patches)
                collectors_futures.append((patch_collector, future))

    for patch_collector, future in collectors_futures:
        patch_collectors.append((patch_collector, future.result()))
        patch_collector.delete_repo()

    patches_futures = []
    for patch_collector, bug_patches in patch_collectors:
        bug_patches_len = len(bug_patches)

        for i, bug_patch in enumerate(bug_patches):
            if i == bug_patches_len - 1:
                # Last bug patch for this patch collector deletes the repo
                future = executor.submit(patch_collector.test_patch, bug_patch, True)
            else:
                future = executor.submit(patch_collector.test_patch, bug_patch)
            patches_futures.append((bug_patch, future))

    for bug_patch, future in patches_futures:
        is_patch = future.result()
        if is_patch:
            data_path = os.path.join(results_path, bug_patch.repo.full_name.replace('/', '-') + '.json')
            with open(data_path, "a") as fp:
                data = bug_patch.get_data()
                fp.write((json.dumps(data) + "\n"))


def main():
    fire.Fire(collect_bugs)


if __name__ == '__main__':
    sys.exit(main())
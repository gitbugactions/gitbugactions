import os
import sys
import uuid
import json
import json
import shutil
import pygit2
import tempfile
import logging
import copy
import threading
import fire
from datetime import datetime
from github import Github, Repository
from unidiff import PatchSet
from crawlergpt.actions.actions import GitHubActions
from concurrent.futures import ThreadPoolExecutor

class BugPatch:
    def __init__(self, repo, commit, previous_commit, bug_patch, test_patch):
        self.repo = repo
        self.commit = commit.hex
        self.commit_message = commit.message
        self.previous_commit = previous_commit.hex
        self.bug_patch = bug_patch
        self.test_patch = test_patch

    def get_data(self):
        return { 
            'repository': self.repo.full_name,
            'clone_url': self.repo.clone_url,
            'timestamp': datetime.utcnow().isoformat() + "Z",
            'commit_hash': self.commit,
            'commit_message': self.commit_message,
            'bug_patch': str(self.bug_patch),
            'test_patch': str(self.test_patch)
        }


class PatchCollector:
    def __init__(self, repo: Repository):
        self.repo = repo
        self.language = repo.language
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
        self.repo_clone = pygit2.clone_repository(
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
    
    def __run_tests(self, repo_clone):
        res = []
        workflow_succeeded = False

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
            failed_tests, _, _ = test_actions.run_workflow(workflow)
            if failed_tests is None:
                # Timeout: The other commits will take similar amount of time FIXME
                # Job failed without tests failing
                logging.info(f"{self.repo.full_name}: failed tests")
                continue
            
            res.extend(failed_tests)
            workflow_succeeded = True
        test_actions.delete_workflows()

        return res, workflow_succeeded
    
    def __get_diff_tests(self, commit_hex, previous_commit_hex, test_patch):
        previous_failed_tests = []
        current_failed_tests = []
        pre_workflow_succeeded = False
        cur_workflow_succeeded = False

        if not self.cloned:
            self.__clone_repo()

        new_repo_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
        shutil.copytree(self.repo_path, new_repo_path)

        try:
            repo_clone = pygit2.Repository(os.path.join(new_repo_path, ".git"))
            first_commit = repo_clone.revparse_single(self.first_commit.hex)
            repo_clone.reset(first_commit.oid, pygit2.GIT_RESET_HARD)
            commit = repo_clone.revparse_single(commit_hex)
            previous_commit = repo_clone.revparse_single(previous_commit_hex)

            # Apply diff and run tests
            repo_clone.checkout_tree(previous_commit)
            # Creates ref to avoid "failed to identify reference"
            repo_clone.create_tag(str(uuid.uuid4()), previous_commit.oid, pygit2.GIT_OBJ_COMMIT, previous_commit.author, previous_commit.message)
            repo_clone.set_head(previous_commit.oid)
            try:
                repo_clone.apply(pygit2.Diff.parse_diff(str(test_patch)))
            except pygit2.GitError:
                # Invalid patches
                return current_failed_tests, previous_failed_tests, False
            previous_failed_tests, pre_workflow_succeeded = self.__run_tests(repo_clone)

            repo_clone.checkout_tree(commit)
            # Creates ref to avoid "failed to identify reference"
            repo_clone.create_tag(str(uuid.uuid4()), commit.oid, pygit2.GIT_OBJ_COMMIT, \
                                    commit.author, commit.message)
            repo_clone.set_head(commit.oid)
            current_failed_tests, cur_workflow_succeeded = self.__run_tests(repo_clone)
            workflow_succeeded = pre_workflow_succeeded and cur_workflow_succeeded
        finally:
            shutil.rmtree(new_repo_path)

        return current_failed_tests, previous_failed_tests, workflow_succeeded
    
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
            # Ignore commits without tests
            # FIXME check if test_patch only has deletes
            if len(test_patch) == 0 or len(bug_patch) == 0:
                logging.info(f"Skipping commit {self.repo.full_name} {commit.hex}: no test/bug patch")
                continue

            patches.append(BugPatch(self.repo, commit, previous_commit, bug_patch, test_patch))
        
        return patches

    def test_patch(self, bug_patch: BugPatch, delete_repo = False):
        current_failed_tests, previous_failed_tests, workflow_succeeded = \
            self.__get_diff_tests(bug_patch.commit, bug_patch.previous_commit, bug_patch.test_patch)
        failed_diff = list(set(x.classname + "#" + x.name for x in previous_failed_tests)
                            .difference(set(x.classname + "#" + x.name for x in current_failed_tests)))

        if delete_repo:
            self.delete_repo()

        # FIXME check only if the current commit passed
        # Check the tests that failed in the previous commit
        # Save the tests that failed
        if len(failed_diff) == 0 or not workflow_succeeded:
            logging.info(f"Skipping commit {self.repo.full_name} {bug_patch.commit}: no failed diff")
            return False

        return True
    
    def delete_repo(self):
        if hasattr(self, "repo_path") and os.path.exists(self.repo_path):
            shutil.rmtree(self.repo_path)
        self.cloned = False


def collect_bugs(data_path, results_path="data/out_bugs", n_workers=1):
    if "GITHUB_ACCESS_TOKEN" in os.environ:
        token = os.environ["GITHUB_ACCESS_TOKEN"]
    else:
        logging.warning("No GITHUB_ACCESS_TOKEN provided.")
        token = None
    
    github: Github = Github(
        login_or_token=token, 
        per_page=100, 
    )

    executor = ThreadPoolExecutor(max_workers=n_workers)
    collectors_futures = []
    patch_collectors = []

    # FIXME save times of each action
    # Save total time
    # Save RAM used?
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
        if future.result():
            data_path = os.path.join(results_path, bug_patch.repo.full_name.replace('/', '-') + '.json')
            with open(data_path, "a") as fp:
                fp.write((json.dumps(bug_patch.get_data()) + "\n"))


def main():
    fire.Fire(collect_bugs)


if __name__ == '__main__':
    sys.exit(main())
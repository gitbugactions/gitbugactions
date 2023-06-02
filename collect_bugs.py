import os
import sys
import uuid
import json
import json
import shutil
import pygit2
import tempfile
import logging
from datetime import datetime
from github import Github, Repository
from unidiff import PatchSet
from crawlergpt.act import GitHubTestActions
from crawlergpt.crawler import RateLimiter
from concurrent.futures import ThreadPoolExecutor

class BugPatch:
    def __init__(self, repo, commit, previous_commit, bug_patch, test_patch):
        self.repo = repo
        self.commit = commit.hex
        self.previous_commit = previous_commit.hex
        self.bug_patch = bug_patch
        self.test_patch = test_patch

    def get_data(self):
        return { 
            'repository': self.repo.full_name,
            'clone_url': self.repo.clone_url,
            'timestamp': datetime.utcnow().isoformat() + "Z",
            'commit_hash': self.commit.hex,
            'commit_message': self.commit.message,
            'bug_patch': str(self.bug_patch),
            'test_patch': str(self.test_patch)
        }


# FIXME identify build tool
class PatchCollector:
    def __init__(self, repo: Repository):
        self.repo = repo
        self.cloned = False

    def __clone_repo(self):
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

    def __get_default_actions(self):
        if len(list(self.repo_clone.references.iterator())) == 0:
            return
        first_commit = None

        for commit in self.repo_clone.walk(self.repo_clone.head.target):
            if first_commit is None:
                first_commit = commit
            self.repo_clone.checkout_tree(commit)
            self.repo_clone.set_head(commit.oid)
            actions = GitHubTestActions(self.repo_path)
            if len(actions.test_workflows) > 0:
                self.default_actions = actions

        self.repo_clone.reset(first_commit.oid, pygit2.GIT_RESET_HARD)
        
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

        test_actions = GitHubTestActions(repo_clone.workdir)
        if len(test_actions.test_workflows) == 0:
            test_actions = self.default_actions
        test_actions.save_workflows()

        for workflow in test_actions.test_workflows:
            failed_tests, _, _ = test_actions.get_failed_tests(workflow)
            if failed_tests is None:
                # Timeout: The other commits will take similar amount of time FIXME
                # Job failed without tests failing
                logging.info(f"{self.repo.full_name}: failed current tests")
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
        if self.cloned and os.path.exists(self.repo_path):
            shutil.rmtree(self.repo_path)
        self.cloned = False


if __name__ == '__main__':
    rate_limiter = RateLimiter()
    github: Github = Github(
        login_or_token=os.environ["GITHUB_ACCESS_TOKEN"], 
        per_page=100, 
    )
    path = sys.argv[1]

    dir_list = os.listdir(path)

    if len(sys.argv) == 3:
        n_workers = int(sys.argv[2])
    else:
        n_workers = 1

    executor = ThreadPoolExecutor(max_workers=n_workers)
    collectors_futures = []
    patch_collectors = []

    # FIXME save times of each action
    # Save total time
    # Save RAM used?
    for file in dir_list:
        with open(os.path.join(path, file), "r") as f:
            run = json.loads(f.read())
            name = run["repository"].replace("/", "-")
            if not os.path.exists("data/out_bugs"):
                os.mkdir("data/out_bugs")

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
            data_path = os.path.join("data/out_bugs", bug_patch.repo.full_name.replace('/', '-'))
            with open(data_path, "w") as fp:
                fp.write((json.dumps(bug_patch.get_data()) + "\n"))

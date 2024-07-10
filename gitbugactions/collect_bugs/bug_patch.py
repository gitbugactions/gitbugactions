import uuid
import pygit2
import datetime
from typing import List, Any, Dict, Set, Optional
from enum import Enum
from github import Repository
from gitbugactions.github_api import GithubAPI
from unidiff import PatchSet
from gitbugactions.actions.actions import ActTestsRun
from gitbugactions.actions.action import Action
from gitbugactions.test_executor import TestExecutor
from gitbugactions.util import get_patch_file_extensions


class ChangeType(Enum):
    SOURCE_ONLY = 0
    MIXED = 1
    NON_CODE_ONLY = 2

    @staticmethod
    def get_change_type(bug_patch: PatchSet, non_code_patch: PatchSet) -> "ChangeType":
        if len(bug_patch) > 0 and len(non_code_patch) > 0:
            return ChangeType.MIXED
        elif len(bug_patch) > 0:
            return ChangeType.SOURCE_ONLY
        else:
            return ChangeType.NON_CODE_ONLY


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
        self.commit: str = str(commit.id)
        self.commit_message: str = commit.message
        self.commit_timestamp: str = (
            datetime.datetime.fromtimestamp(
                int(commit.commit_time), datetime.UTC
            ).isoformat()
            + "Z"
        )
        self.previous_commit: str = str(previous_commit.id)
        self.previous_commit_message: str = previous_commit.message
        self.previous_commit_timestamp: str = (
            datetime.datetime.fromtimestamp(
                int(previous_commit.commit_time), datetime.UTC
            ).isoformat()
            + "Z"
        )
        self.time_to_patch: str = str(
            datetime.datetime.fromtimestamp(int(commit.commit_time), datetime.UTC)
            - datetime.datetime.fromtimestamp(
                int(previous_commit.commit_time), datetime.UTC
            )
        )
        self.bug_patch: PatchSet = self.__clean_patch(bug_patch)
        self.bug_patch_file_extensions: List[str] = get_patch_file_extensions(
            self.bug_patch
        )
        self.test_patch: PatchSet = self.__clean_patch(test_patch)
        self.test_patch_file_extensions: List[str] = get_patch_file_extensions(
            self.test_patch
        )
        self.non_code_patch: PatchSet = self.__clean_patch(non_code_patch)
        self.non_code_patch_file_extensions: List[str] = get_patch_file_extensions(
            self.non_code_patch
        )
        self.change_type: ChangeType = ChangeType.get_change_type(
            self.bug_patch, self.non_code_patch
        )
        self.actions: Set[Action] = actions
        self.strategy_used: str = "UNKNOWN"
        self.issues = None
        # The actions are grouped by each phase of the strategy used
        self.actions_runs: List[List[ActTestsRun]] = []

    def __flat_failed_tests(self, runs):
        return sum(map(lambda act_run: act_run.failed_tests, runs), [])

    @property
    def prev_commit_passed(self):
        return (
            self.actions_runs[0] is not None
            and len(self.__flat_failed_tests(self.actions_runs[0])) == 0
        )

    @property
    def prev_with_diff_failed(self):
        return (
            self.actions_runs[1] is not None
            and len(self.__flat_failed_tests(self.actions_runs[1])) > 0
        )

    @property
    def curr_commit_passed(self):
        return (
            self.actions_runs[2] is not None
            and len(self.__flat_failed_tests(self.actions_runs[2])) == 0
        )

    @property
    def curr_commit_failed(self):
        return (
            self.actions_runs[2] is not None
            and len(self.__flat_failed_tests(self.actions_runs[2])) > 0
        )

    @property
    def prev_commit_failed(self):
        return (
            self.actions_runs[0] is not None
            and len(self.__flat_failed_tests(self.actions_runs[0])) > 0
        )

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
            "collection_timestamp": datetime.datetime.now(datetime.UTC).isoformat()
            + "Z",
            "commit_hash": self.commit,
            "commit_message": self.commit_message,
            "commit_timestamp": self.commit_timestamp,
            "previous_commit_hash": self.previous_commit,
            "previous_commit_message": self.previous_commit_message,
            "previous_commit_timestamp": self.previous_commit_timestamp,
            "time_to_patch": self.time_to_patch,
            "bug_patch": str(self.bug_patch),
            "bug_patch_file_extensions": self.bug_patch_file_extensions,
            "test_patch": str(self.test_patch),
            "test_patch_file_extensions": self.test_patch_file_extensions,
            "non_code_patch": str(self.non_code_patch),
            "non_code_patch_file_extensions": self.non_code_patch_file_extensions,
            "change_type": self.change_type.name,
            "actions_runs": actions_runs,
            "strategy": self.strategy_used,
            "issues": self.issues,
        }

    def __clean_patch(self, patch: PatchSet) -> PatchSet:
        """
        Cleans the patch to be used by pygit2. This is related to issue XXX that causes libgit2 to segfault when one of the paths is /dev/null.
        """
        for file in patch:
            if file.source_file == "/dev/null" and not file.is_added_file:
                file.source_file = file.target_file.replace("b/", "a/", 1)
            elif file.target_file == "/dev/null" and not file.is_removed_file:
                file.target_file = file.source_file.replace("a/", "b/", 1)
        return patch

    def __set_commit(self, repo_clone: pygit2.Repository, commit: str):
        commit = repo_clone.revparse_single(commit)
        repo_clone.checkout_tree(commit)
        repo_clone.create_tag(
            str(uuid.uuid4()),
            commit.id,
            pygit2.GIT_OBJECT_COMMIT,
            commit.author,
            commit.message,
        )
        repo_clone.set_head(commit.id)

    def __apply_non_code_patch(self, repo_clone: pygit2.Repository):
        # We only apply the non code patch when the bug patch is non-empty
        # Otherwise, we are testing the non code patch alone
        if len(self.non_code_patch) > 0 and len(self.bug_patch) > 0:
            try:
                repo_clone.apply(pygit2.Diff.parse_diff(str(self.non_code_patch)))
                return True
            except pygit2.GitError:
                # Invalid patches
                return False
        return True

    def __apply_test_patch(self, repo_clone: pygit2.Repository):
        try:
            repo_clone.apply(pygit2.Diff.parse_diff(str(self.test_patch)))
            return True
        except pygit2.GitError:
            # Invalid patches
            return False

    def test_previous_commit(
        self,
        executor: TestExecutor,
        offline: bool = False,
        keep_containers: bool = False,
    ) -> Optional[List[ActTestsRun]]:
        executor.reset_repo()
        self.__set_commit(executor.repo_clone, self.previous_commit)
        if not self.__apply_non_code_patch(executor.repo_clone):
            return None
        return executor.run_tests(offline=offline, keep_containers=keep_containers)

    def test_previous_commit_with_diff(
        self,
        executor: TestExecutor,
        offline: bool = False,
        keep_containers: bool = False,
    ) -> Optional[List[ActTestsRun]]:
        executor.reset_repo()
        self.__set_commit(executor.repo_clone, self.previous_commit)
        if not self.__apply_non_code_patch(executor.repo_clone):
            return None
        if not self.__apply_test_patch(executor.repo_clone):
            return None
        return executor.run_tests(offline=offline, keep_containers=keep_containers)

    def test_current_commit(
        self,
        executor: TestExecutor,
        offline: bool = False,
        keep_containers: bool = False,
    ) -> Optional[List[ActTestsRun]]:
        executor.reset_repo()
        self.__set_commit(executor.repo_clone, self.commit)
        return executor.run_tests(offline=offline, keep_containers=keep_containers)

    @staticmethod
    def from_dict(bug: Dict[str, Any], repo_clone: pygit2.Repository) -> "BugPatch":
        github = GithubAPI()
        repo_full_name = bug["repository"]

        return BugPatch(
            github.get_repo(repo_full_name),
            repo_clone.revparse_single(bug["commit_hash"]),
            repo_clone.revparse_single(bug["previous_commit_hash"]),
            PatchSet(bug["bug_patch"]),
            PatchSet(bug["test_patch"]),
            PatchSet(bug["non_code_patch"]),
            set(),
        )

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

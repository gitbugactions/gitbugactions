import datetime
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Set
import re

import pygit2
from github import Repository
from unidiff import PatchSet

from gitbugactions.actions.action import Action
from gitbugactions.actions.actions import ActTestsRun
from gitbugactions.commit_execution.executor import CommitExecutor
from gitbugactions.commit_execution.results import CommitExecutionResult
from gitbugactions.github_api import GithubAPI
from gitbugactions.utils.file_utils import get_patch_file_extensions
from gitbugactions.utils.repo_utils import git_clean


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
        # The execution results for each phase of the strategy
        self.execution_results: List[Optional[CommitExecutionResult]] = [
            None,
            None,
            None,
        ]

    @property
    def prev_commit_passed(self):
        """Check if the previous commit passed all tests."""
        return (
            self.execution_results[0] is not None
            and self.execution_results[0].success
            and self.execution_results[0].failed_count == 0
        )

    @property
    def prev_with_diff_failed(self):
        """Check if the previous commit with diff failed any tests."""
        return self.execution_results[1] is not None and (
            not self.execution_results[1].success
            or self.execution_results[1].failed_count > 0
        )

    @property
    def curr_commit_passed(self):
        """Check if the current commit passed all tests."""
        return (
            self.execution_results[2] is not None
            and self.execution_results[2].success
            and self.execution_results[2].failed_count == 0
        )

    @property
    def curr_commit_failed(self):
        """Check if the current commit failed any tests."""
        return self.execution_results[2] is not None and (
            not self.execution_results[2].success
            or self.execution_results[2].failed_count > 0
        )

    @property
    def prev_commit_failed(self):
        """Check if the previous commit failed any tests."""
        return self.execution_results[0] is not None and (
            not self.execution_results[0].success
            or self.execution_results[0].failed_count > 0
        )

    def get_data(self):
        """Get a dictionary representation of the bug patch for serialization."""
        execution_results = []

        for result in self.execution_results:
            if result is None:
                execution_results.append(None)
                continue

            # Convert CommitExecutionResult to a serializable dictionary
            result_data = {
                "commit_sha": result.commit_sha,
                "success": result.success,
                "execution_time": result.execution_time,
                "workflows_executed": result.workflows_executed,
                "all_workflows": result.all_workflows,
                "test_workflows": result.test_workflows,
                "all_build_tools": result.all_build_tools,
                "test_build_tools": result.test_build_tools,
                "patches_applied": result.patches_applied,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "test_results": [
                    {
                        "name": test.name,
                        "classname": test.classname,
                        "result": test.result,
                        "message": test.message,
                        "time": test.time,
                        "stdout": test.stdout,
                        "stderr": test.stderr,
                    }
                    for test in result.test_results
                ],
                "total_tests": result.total_tests,
                "passed_count": result.passed_count,
                "failed_count": result.failed_count,
                "skipped_count": result.skipped_count,
                "error_count": result.error_count,
            }
            execution_results.append(result_data)

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
            "execution_results": execution_results,
            "strategy": self.strategy_used,
            "issues": self.issues,
        }

    def __clean_patch(self, patch: PatchSet) -> PatchSet:
        """
        Cleans the patch to be used by pygit2. This is related to an issue that causes libgit2 to segfault when one of the paths is /dev/null.
        """
        for file in patch:
            if file.source_file == "/dev/null" and not file.is_added_file:
                file.source_file = file.target_file.replace("b/", "a/", 1)
            elif file.target_file == "/dev/null" and not file.is_removed_file:
                file.target_file = file.source_file.replace("a/", "b/", 1)
        return patch

    def test_previous_commit(
        self,
        executor: CommitExecutor,
        offline: bool = False,
    ) -> Optional[CommitExecutionResult]:
        """
        Test the previous commit with the non-code patch applied.

        Args:
            executor: CommitExecutor instance
            offline: Whether to run in offline mode

        Returns:
            CommitExecutionResult or None if execution failed
        """
        try:
            # Execute at the previous commit
            result = executor.execute_at_commit(self.previous_commit)

            # If non-code patch exists and bug patch exists, apply the non-code patch
            if len(self.non_code_patch) > 0 and len(self.bug_patch) > 0:
                # Apply non-code patch and execute again
                result = executor.execute_at_commit_with_patches(
                    self.previous_commit, patches=[self.non_code_patch]
                )

            return result
        except Exception as e:
            # Log the error and return None to indicate failure
            import logging

            logging.error(f"Error testing previous commit: {str(e)}")
            return None

    def test_previous_commit_with_diff(
        self,
        executor: CommitExecutor,
        offline: bool = False,
    ) -> Optional[CommitExecutionResult]:
        """
        Test the previous commit with both non-code patch and test patch applied.

        Args:
            executor: CommitExecutor instance
            offline: Whether to run in offline mode

        Returns:
            CommitExecutionResult or None if execution failed
        """
        try:
            # Apply both non-code and test patches to the previous commit
            patches = []
            if len(self.non_code_patch) > 0 and len(self.bug_patch) > 0:
                patches.append(self.non_code_patch)
            if len(self.test_patch) > 0:
                patches.append(self.test_patch)

            # Execute with patches
            result = executor.execute_at_commit_with_patches(
                self.previous_commit, patches=patches
            )

            return result
        except Exception as e:
            # Log the error and return None to indicate failure
            import logging

            logging.error(f"Error testing previous commit with diff: {str(e)}")
            return None

    def test_current_commit(
        self,
        executor: CommitExecutor,
        offline: bool = False,
    ) -> Optional[CommitExecutionResult]:
        """
        Test the current commit.

        Args:
            executor: CommitExecutor instance
            offline: Whether to run in offline mode

        Returns:
            CommitExecutionResult or None if execution failed
        """
        try:
            # Execute at the current commit
            result = executor.execute_at_commit(self.commit)

            return result
        except Exception as e:
            # Log the error and return None to indicate failure
            import logging

            logging.error(f"Error testing current commit: {str(e)}")
            return None

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
            set(),  # Empty set for actions
        )

    def __remove_patch_index(self, patch: PatchSet) -> str:
        """Remove the index from the patch to avoid false positives in the hash."""
        return re.sub(r"index [a-f0-9]+\.\.[a-f0-9]+", "", str(patch))

    def __hash__(self):
        """Hash based on the content of the patches."""
        return hash(
            (
                self.__remove_patch_index(self.bug_patch),
                self.__remove_patch_index(self.test_patch),
                self.__remove_patch_index(self.non_code_patch),
            )
        )

    def __eq__(self, __value: object) -> bool:
        """Equality based on the content of the patches."""
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
        """Inequality based on the content of the patches."""
        return not self.__eq__(__value)

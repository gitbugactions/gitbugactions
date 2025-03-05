from abc import ABC, abstractmethod
from typing import List, Optional

from gitbugactions.collect_bugs.bug_patch import BugPatch
from gitbugactions.commit_execution.results import CommitExecutionResult


class CollectionStrategy(ABC):
    @staticmethod
    def _diff_tests(
        failed_result: CommitExecutionResult, passed_result: CommitExecutionResult
    ):
        """
        Find tests that were fixed between two executions.

        Args:
            failed_result: The execution result with failed tests
            passed_result: The execution result with passed tests

        Returns:
            Tuple of (fixed_tests, not_fixed_tests)
        """
        fixed, not_fixed = [], []

        # Get all failed tests from the failed result
        for failed_test in failed_result.test_results:
            if failed_test.result == "failed":
                # Check if this test is now passing in the passed_result
                found_fixed = False
                for test in passed_result.test_results:
                    if (
                        failed_test.classname == test.classname
                        and failed_test.name == test.name
                        and test.result == "passed"
                    ):
                        fixed.append(failed_test)
                        found_fixed = True
                        break

                if not found_fixed:
                    not_fixed.append(failed_test)

        return fixed, not_fixed

    @staticmethod
    def _check_tests_were_fixed(
        failed_result: CommitExecutionResult, passed_result: CommitExecutionResult
    ):
        """
        Check if all failed tests were fixed.

        Args:
            failed_result: The execution result with failed tests
            passed_result: The execution result with passed tests

        Returns:
            True if all failed tests were fixed, False otherwise
        """
        _, not_fixed = CollectionStrategy._diff_tests(failed_result, passed_result)
        return len(not_fixed) == 0

    @staticmethod
    def _number_of_tests(result: Optional[CommitExecutionResult]):
        """
        Get the total number of tests in an execution result.

        Args:
            result: The execution result

        Returns:
            The total number of tests
        """
        if result is None:
            return 0
        return result.total_tests

    @abstractmethod
    def check(self, bug_patch: BugPatch) -> bool:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass


class UnknownStrategy(CollectionStrategy):
    def check(self, bug_patch: BugPatch) -> bool:
        return False

    @property
    def name(self) -> str:
        return "UNKNOWN"


class PassPassStrategy(CollectionStrategy):
    def check(self, bug_patch: BugPatch) -> bool:
        return (
            # previous commit passed
            bug_patch.prev_commit_passed
            # previous commit with new tests failed
            and bug_patch.prev_with_diff_failed
            # current commit passed
            and bug_patch.curr_commit_passed
            # test patch is not empty
            and len(bug_patch.test_patch) > 0
            # test patch is not removals only
            and not (
                bug_patch.test_patch.removed > 0 and bug_patch.test_patch.added == 0
            )
            # check if tests from previous commit w/diff were fixed
            and bug_patch.execution_results[1] is not None
            and bug_patch.execution_results[2] is not None
            and CollectionStrategy._check_tests_were_fixed(
                bug_patch.execution_results[1], bug_patch.execution_results[2]
            )
            # previous commit should have at least the same number of tests than current commit
            and CollectionStrategy._number_of_tests(bug_patch.execution_results[0])
            <= CollectionStrategy._number_of_tests(bug_patch.execution_results[2])
            # current commit should have same number of tests as previous commit w/ tests
            and CollectionStrategy._number_of_tests(bug_patch.execution_results[2])
            == CollectionStrategy._number_of_tests(bug_patch.execution_results[1])
        )

    @property
    def name(self) -> str:
        return "PASS_PASS"


class FailPassStrategy(CollectionStrategy):
    def check(self, bug_patch: BugPatch) -> bool:
        return (
            # previous commit failed
            bug_patch.prev_commit_failed
            # no changes have been made in the tests
            and len(bug_patch.test_patch) == 0
            # current commit passed
            and bug_patch.curr_commit_passed
            # check if tests from previous commit were fixed
            and bug_patch.execution_results[0] is not None
            and bug_patch.execution_results[2] is not None
            and CollectionStrategy._check_tests_were_fixed(
                bug_patch.execution_results[0], bug_patch.execution_results[2]
            )
            # previous commit should have same number of tests as current commit
            and CollectionStrategy._number_of_tests(bug_patch.execution_results[0])
            == CollectionStrategy._number_of_tests(bug_patch.execution_results[2])
        )

    @property
    def name(self) -> str:
        return "FAIL_PASS"


class FailFailStrategy(CollectionStrategy):
    def check(self, bug_patch: BugPatch) -> bool:
        return (
            # previous commit failed
            bug_patch.prev_commit_failed
            # current commit failed
            and bug_patch.curr_commit_failed
            # at least one test was fixed
            and bug_patch.execution_results[0] is not None
            and bug_patch.execution_results[2] is not None
            and len(
                CollectionStrategy._diff_tests(
                    bug_patch.execution_results[0], bug_patch.execution_results[2]
                )[0]
            )
            > 0
            # previous commit should have same number of tests as current commit
            and CollectionStrategy._number_of_tests(bug_patch.execution_results[0])
            == CollectionStrategy._number_of_tests(bug_patch.execution_results[2])
        ) or (
            # previous commit with diff failed
            bug_patch.prev_with_diff_failed
            # current commit failed
            and bug_patch.curr_commit_failed
            # at least one test was fixed
            and bug_patch.execution_results[1] is not None
            and bug_patch.execution_results[2] is not None
            and len(
                CollectionStrategy._diff_tests(
                    bug_patch.execution_results[1], bug_patch.execution_results[2]
                )[0]
            )
            > 0
            # previous commit w/test diff should have same number of tests as current commit
            and CollectionStrategy._number_of_tests(bug_patch.execution_results[1])
            == CollectionStrategy._number_of_tests(bug_patch.execution_results[2])
        )

    @property
    def name(self) -> str:
        return "FAIL_FAIL"


class FailPassBuildStrategy(CollectionStrategy):
    def check(self, bug_patch: BugPatch) -> bool:
        return (
            (
                # tests failed in the previous commit
                bug_patch.prev_commit_failed
                # or the run failed
                or (
                    bug_patch.execution_results[0] is not None
                    and not bug_patch.execution_results[0].success
                )
            )
            # tests passed in the current commit
            and bug_patch.curr_commit_passed
        ) or (
            (
                # tests failed in the previous commit w/diff
                bug_patch.prev_with_diff_failed
                # or the run failed
                or (
                    bug_patch.execution_results[1] is not None
                    and not bug_patch.execution_results[1].success
                )
            )
            # tests passed in the current commit
            and bug_patch.curr_commit_passed
        )

    @property
    def name(self) -> str:
        return "FAIL_PASS_BUILD"

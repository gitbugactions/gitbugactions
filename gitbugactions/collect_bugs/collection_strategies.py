from abc import ABC, abstractmethod
from typing import List
from gitbugactions.collect_bugs.bug_patch import BugPatch
from gitbugactions.actions.actions import ActTestsRun


class CollectionStrategy(ABC):
    @staticmethod
    def _diff_tests(run_failed: List[ActTestsRun], run_passed: List[ActTestsRun]):
        flat_failed_tests = sum(
            map(lambda act_run: act_run.failed_tests, run_failed), []
        )
        flat_tests = sum(map(lambda act_run: act_run.tests, run_passed), [])
        fixed, not_fixed = [], []

        for failed_test in flat_failed_tests:
            for test in flat_tests:
                if (
                    failed_test.classname == test.classname
                    and failed_test.name == test.name
                    and test.is_passed
                ):
                    fixed.append(failed_test)
                    break
            else:
                not_fixed.append(failed_test)

        return fixed, not_fixed

    @staticmethod
    def _check_tests_were_fixed(
        run_failed: List[ActTestsRun], run_passed: List[ActTestsRun]
    ):
        _, not_fixed = CollectionStrategy._diff_tests(run_failed, run_passed)
        return len(not_fixed) == 0

    @staticmethod
    def _number_of_tests(runs):
        return sum(map(lambda act_run: len(act_run.tests), runs))

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
            and CollectionStrategy._check_tests_were_fixed(
                bug_patch.actions_runs[1], bug_patch.actions_runs[2]
            )
            # previous commit should have at least the same number of tests than current commit
            and CollectionStrategy._number_of_tests(bug_patch.actions_runs[0])
            <= CollectionStrategy._number_of_tests(bug_patch.actions_runs[2])
            # current commit should have same number of tests as previous commit w/ tests
            and CollectionStrategy._number_of_tests(bug_patch.actions_runs[2])
            == CollectionStrategy._number_of_tests(bug_patch.actions_runs[1])
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
            and CollectionStrategy._check_tests_were_fixed(
                bug_patch.actions_runs[0], bug_patch.actions_runs[2]
            )
            # previous commit should have same number of tests as current commit
            and CollectionStrategy._number_of_tests(bug_patch.actions_runs[0])
            == CollectionStrategy._number_of_tests(bug_patch.actions_runs[2])
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
            and len(
                CollectionStrategy._diff_tests(
                    bug_patch.actions_runs[0], bug_patch.actions_runs[2]
                )[0]
            )
            > 0
            # previous commit should have same number of tests as current commit
            and CollectionStrategy._number_of_tests(bug_patch.actions_runs[0])
            == CollectionStrategy._number_of_tests(bug_patch.actions_runs[2])
        ) or (
            # previous commit with diff failed
            bug_patch.prev_with_diff_failed
            # current commit failed
            and bug_patch.curr_commit_failed
            # at least one test was fixed
            and len(
                CollectionStrategy._diff_tests(
                    bug_patch.actions_runs[1], bug_patch.actions_runs[2]
                )[0]
            )
            > 0
            # previous commit w/test diff should have same number of tests as current commit
            and CollectionStrategy._number_of_tests(bug_patch.actions_runs[1])
            == CollectionStrategy._number_of_tests(bug_patch.actions_runs[2])
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
                    bug_patch.actions_runs[0] is not None
                    and any(map(lambda run: run.failed, bug_patch.actions_runs[0]))
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
                    bug_patch.actions_runs[1] is not None
                    and any(map(lambda run: run.failed, bug_patch.actions_runs[1]))
                )
            )
            # tests passed in the current commit
            and bug_patch.curr_commit_passed
        )

    @property
    def name(self) -> str:
        return "FAIL_PASS_BUILD"

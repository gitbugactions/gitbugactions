"""
Result classes for the commit execution module.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union


@dataclass
class TestResult:
    """
    Result of a single test execution.

    Attributes:
        name: Name of the test
        classname: Class name of the test
        result: Result of the test (passed, failed, skipped, error)
        success: Whether the test passed
        execution_time: Time taken to execute the test
        message: Optional message associated with the test result
        time: Time taken to execute the test (deprecated, use execution_time)
        stdout: Standard output of the test
        stderr: Standard error of the test
    """

    name: str
    classname: str
    result: str  # "passed", "failed", "skipped", "error"
    message: Optional[str] = None
    time: float = 0.0
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    
    @property
    def success(self) -> bool:
        """
        Check if the test passed.

        Returns:
            True if the test passed, False otherwise
        """
        return self.is_passed
        
    @property
    def execution_time(self) -> float:
        """
        Get the execution time of the test.

        Returns:
            Time taken to execute the test
        """
        return self.time

    @property
    def is_passed(self) -> bool:
        """
        Check if the test passed.

        Returns:
            True if the test passed, False otherwise
        """
        return self.result == "passed"

    @property
    def is_failed(self) -> bool:
        """
        Check if the test failed.

        Returns:
            True if the test failed, False otherwise
        """
        return self.result == "failed"

    @property
    def is_skipped(self) -> bool:
        """
        Check if the test was skipped.

        Returns:
            True if the test was skipped, False otherwise
        """
        return self.result == "skipped"

    @property
    def is_error(self) -> bool:
        """
        Check if the test resulted in an error.

        Returns:
            True if the test resulted in an error, False otherwise
        """
        return self.result == "error"

    @property
    def full_name(self) -> str:
        """
        Get the full name of the test.

        Returns:
            Full name of the test (classname.name)
        """
        return f"{self.classname}.{self.name}"


@dataclass
class CommitExecutionResult:
    """
    Result of executing tests at a specific commit.

    Attributes:
        commit_sha: SHA of the commit
        success: Whether the execution was successful
        execution_time: Time taken for the execution
        test_results: List of test results
        workflows_executed: List of workflows that were executed
        all_workflows: List of all workflows available in the repository
        test_workflows: List of all test workflows available in the repository
        all_build_tools: List of all build tools available in the repository
        test_build_tools: List of test build tools available in the repository
        patches_applied: Dictionary mapping patch types to whether they were applied
        stdout: Standard output of the execution
        stderr: Standard error of the execution
    """

    commit_sha: str
    success: bool
    execution_time: float
    workflows_executed: List[str] = field(default_factory=list)
    test_results: List[TestResult] = field(default_factory=list)
    all_workflows: List[str] = field(default_factory=list)
    test_workflows: List[str] = field(default_factory=list)
    all_build_tools: List[str] = field(default_factory=list)
    test_build_tools: List[str] = field(default_factory=list)
    patches_applied: Dict[str, bool] = field(default_factory=dict)
    stdout: Optional[str] = None
    stderr: Optional[str] = None

    @property
    def passed_tests(self) -> List[TestResult]:
        """
        Get the list of passed tests.

        Returns:
            List of passed tests
        """
        return [test for test in self.test_results if test.is_passed]

    @property
    def failed_tests(self) -> List[TestResult]:
        """
        Get the list of failed tests.

        Returns:
            List of failed tests
        """
        return [test for test in self.test_results if test.is_failed]

    @property
    def skipped_tests(self) -> List[TestResult]:
        """
        Get the list of skipped tests.

        Returns:
            List of skipped tests
        """
        return [test for test in self.test_results if test.is_skipped]

    @property
    def error_tests(self) -> List[TestResult]:
        """
        Get the list of tests that resulted in an error.

        Returns:
            List of tests that resulted in an error
        """
        return [test for test in self.test_results if test.is_error]

    @property
    def total_tests(self) -> int:
        """
        Get the total number of tests.

        Returns:
            Total number of tests
        """
        return len(self.test_results)

    @property
    def passed_count(self) -> int:
        """
        Get the number of passed tests.

        Returns:
            Number of passed tests
        """
        return len(self.passed_tests)

    @property
    def failed_count(self) -> int:
        """
        Get the number of failed tests.

        Returns:
            Number of failed tests
        """
        return len(self.failed_tests)

    @property
    def skipped_count(self) -> int:
        """
        Get the number of skipped tests.

        Returns:
            Number of skipped tests
        """
        return len(self.skipped_tests)

    @property
    def error_count(self) -> int:
        """
        Get the number of tests that resulted in an error.

        Returns:
            Number of tests that resulted in an error
        """
        return len(self.error_tests)

    def get_test_by_name(self, name: str) -> Optional[TestResult]:
        """
        Get a test by its name.

        Args:
            name: Name of the test to get

        Returns:
            The test result, or None if not found
        """
        for test in self.test_results:
            if test.name == name:
                return test
        return None

    def get_test_by_full_name(self, full_name: str) -> Optional[TestResult]:
        """
        Get a test by its full name (classname.name).

        Args:
            full_name: Full name of the test to get

        Returns:
            The test result, or None if not found
        """
        for test in self.test_results:
            if test.full_name == full_name:
                return test
        return None

    def get_tests_by_classname(self, classname: str) -> List[TestResult]:
        """
        Get all tests with a specific classname.

        Args:
            classname: Class name to filter by

        Returns:
            List of tests with the specified classname
        """
        return [test for test in self.test_results if test.classname == classname]

    def get_tests_by_result(self, result: str) -> List[TestResult]:
        """
        Get all tests with a specific result.

        Args:
            result: Result to filter by (passed, failed, skipped, error)

        Returns:
            List of tests with the specified result
        """
        return [test for test in self.test_results if test.result == result]

    def summary(self) -> str:
        """
        Get a summary of the execution result.

        Returns:
            Summary string
        """
        return (
            f"Commit: {self.commit_sha}\n"
            f"Success: {self.success}\n"
            f"Execution time: {self.execution_time:.2f}s\n"
            f"Workflows executed: {len(self.workflows_executed)}\n"
            f"Total tests: {self.total_tests}\n"
            f"Passed: {self.passed_count}\n"
            f"Failed: {self.failed_count}\n"
            f"Skipped: {self.skipped_count}\n"
            f"Errors: {self.error_count}\n"
        )

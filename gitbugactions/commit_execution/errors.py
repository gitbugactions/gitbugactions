"""
Custom exceptions for the commit execution module.
"""

from typing import List, Optional


class CommitExecutionError(Exception):
    """
    Base class for all commit execution errors.

    Attributes:
        message: Error message
        commit_sha: SHA of the commit where the error occurred
    """

    def __init__(self, message: str, commit_sha: str):
        self.message = message
        self.commit_sha = commit_sha
        super().__init__(message)


class ExecutionError(CommitExecutionError):
    """
    Error that occurs during test execution.

    Attributes:
        message: Error message
        commit_sha: SHA of the commit where the error occurred
        is_infrastructure_error: Whether the error is related to infrastructure
        stdout: Standard output of the execution
        stderr: Standard error of the execution
    """

    def __init__(
        self,
        message: str,
        commit_sha: str,
        is_infrastructure_error: bool = False,
        stdout: Optional[str] = None,
        stderr: Optional[str] = None,
    ):
        self.is_infrastructure_error = is_infrastructure_error
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(message, commit_sha)


class ExecutionTimeoutError(CommitExecutionError):
    """
    Error that occurs when test execution times out.

    Attributes:
        message: Error message
        commit_sha: SHA of the commit where the error occurred
        timeout: Timeout in seconds
        running_workflows: List of workflows that were running when the timeout occurred
    """

    def __init__(
        self,
        message: str,
        commit_sha: str,
        timeout: int,
        running_workflows: List[str],
    ):
        self.timeout = timeout
        self.running_workflows = running_workflows
        super().__init__(message, commit_sha)


class PatchApplicationError(CommitExecutionError):
    """
    Error that occurs when a patch cannot be applied cleanly.

    Attributes:
        message: Error message
        commit_sha: SHA of the commit where the error occurred
        failed_files: List of files that failed to apply
        patch_id: Identifier of the patch that failed to apply
        original_patch: Original patch content
    """

    def __init__(
        self,
        message: str,
        commit_sha: str,
        failed_files: List[str],
        patch_type: str,  # Kept for backward compatibility, renamed in docstring
        original_patch: str,
    ):
        self.failed_files = failed_files
        self.patch_type = patch_type  # Kept for backward compatibility
        self.patch_id = patch_type  # Added for clarity
        self.original_patch = original_patch
        super().__init__(message, commit_sha)

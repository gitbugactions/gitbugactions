"""
Tests for the CommitExecutor class.
"""

import os
import tempfile
import unittest
from unittest import mock
import pytest
import subprocess
import shutil

from gitbugactions.commit_execution import (
    CommitExecutor,
    ExecutionError,
    PatchApplicationError,
)


class TestCommitExecutor(unittest.TestCase):
    """
    Unit tests for the CommitExecutor class.
    """

    def setUp(self):
        """Set up test fixtures."""
        # Create a mock repository URL
        self.repo_url = "https://github.com/example/repo.git"

        # Create a temporary directory for testing
        self.temp_dir = tempfile.mkdtemp(prefix="test_commit_executor_")

        # Mock the clone_repo function
        self.clone_repo_patcher = mock.patch(
            "gitbugactions.commit_execution.executor.clone_repo"
        )
        self.mock_clone_repo = self.clone_repo_patcher.start()

        # Mock the pygit2.Repository
        self.repo_patcher = mock.patch("pygit2.Repository")
        self.mock_repo = self.repo_patcher.start()

        # Mock the subprocess.run
        self.subprocess_run_patcher = mock.patch("subprocess.run")
        self.mock_subprocess_run = self.subprocess_run_patcher.start()

        # Mock the GitHubActions class
        self.github_actions_patcher = mock.patch(
            "gitbugactions.commit_execution.executor.GitHubActions"
        )
        self.mock_github_actions = self.github_actions_patcher.start()

        # Mock the ActCacheDirManager
        self.cache_dir_patcher = mock.patch(
            "gitbugactions.commit_execution.executor.ActCacheDirManager"
        )
        self.mock_cache_dir = self.cache_dir_patcher.start()

        # Set up the mock repository
        self.mock_repo_instance = mock.MagicMock()
        self.mock_clone_repo.return_value = self.mock_repo_instance

        # Set up the mock cache dir
        self.mock_cache_dir.acquire_act_cache_dir.return_value = "/tmp/act_cache"

        # Create the CommitExecutor instance
        self.executor = CommitExecutor(
            repo_url=self.repo_url,
            work_dir=self.temp_dir,
            timeout=60,
        )

    def tearDown(self):
        """Tear down test fixtures."""
        # Stop all patches
        self.clone_repo_patcher.stop()
        self.repo_patcher.stop()
        self.subprocess_run_patcher.stop()
        self.github_actions_patcher.stop()
        self.cache_dir_patcher.stop()

        # Clean up the temporary directory
        self.executor.cleanup()

    def test_execute_at_commit(self):
        """Test executing tests at a specific commit."""
        # Set up mocks for the test
        commit_sha = "abc123"
        mock_commit = mock.MagicMock()
        self.mock_repo_instance.revparse_single.return_value = mock_commit

        # Set up mock for GitHubActions
        mock_actions_instance = mock.MagicMock()
        self.mock_github_actions.return_value = mock_actions_instance

        # Create a mock workflow
        mock_workflow = mock.MagicMock()
        mock_workflow.path = ".github/workflows/test.yml"
        mock_actions_instance.test_workflows = [mock_workflow]

        # Create a mock ActTestsRun
        mock_act_run = mock.MagicMock()
        mock_act_run.workflow = mock_workflow
        mock_act_run.failed = False
        mock_act_run.elapsed_time = 10.5
        mock_act_run.stdout = "Test output"
        mock_act_run.stderr = ""

        # Create a mock test result
        mock_test = mock.MagicMock()
        mock_test.name = "test_example"
        mock_test.classname = "TestClass"
        mock_test.is_passed = True
        mock_test.is_skipped = False
        mock_test.is_error = False
        mock_test.time = 0.5
        mock_test.system_out = "Test stdout"
        mock_test.system_err = ""
        mock_act_run.tests = [mock_test]

        # Set up the mock to return our mock ActTestsRun
        mock_actions_instance.run_workflow.return_value = mock_act_run

        # Execute the test
        result = self.executor.execute_at_commit(commit_sha)

        # Verify the result
        self.assertEqual(result.commit_sha, commit_sha)
        self.assertTrue(result.success)
        self.assertEqual(result.execution_time, 10.5)
        self.assertEqual(len(result.test_results), 1)
        self.assertEqual(result.test_results[0].name, "test_example")
        self.assertEqual(result.test_results[0].classname, "TestClass")
        self.assertEqual(result.test_results[0].result, "passed")

        # Verify the correct methods were called
        self.mock_repo_instance.revparse_single.assert_called_once_with(commit_sha)
        self.mock_repo_instance.checkout_tree.assert_called_once_with(mock_commit)
        mock_actions_instance.run_workflow.assert_called_once()

    def test_execute_at_commit_with_patches(self):
        """Test executing tests at a commit with patches applied."""
        # Set up mocks for the test
        commit_sha = "def456"
        test_patch = """diff --git a/test.js b/test.js
--- a/test.js
+++ b/test.js
@@ -1,1 +1,1 @@
-old
+new
"""

        # Mock the repository operations
        mock_commit = mock.MagicMock()
        self.mock_repo_instance.revparse_single.return_value = mock_commit

        # Mock the apply method to avoid the actual patch application
        # which is causing the error with invalid hex formatted object id
        self.mock_repo_instance.apply = mock.MagicMock(return_value=None)

        # Set up mock for GitHubActions
        mock_actions_instance = mock.MagicMock()
        self.mock_github_actions.return_value = mock_actions_instance

        # Create a mock workflow
        mock_workflow = mock.MagicMock()
        mock_workflow.path = ".github/workflows/test.yml"
        mock_actions_instance.test_workflows = [mock_workflow]

        # Create a mock ActTestsRun
        mock_act_run = mock.MagicMock()
        mock_act_run.workflow = mock_workflow
        mock_act_run.failed = False
        mock_act_run.elapsed_time = 5.2
        mock_act_run.stdout = "Test output"
        mock_act_run.stderr = ""
        mock_act_run.tests = []  # No tests for simplicity

        # Set up the mock to return our mock ActTestsRun
        mock_actions_instance.run_workflow.return_value = mock_act_run

        # Execute the test
        result = self.executor.execute_at_commit_with_patches(
            commit_sha=commit_sha,
            patches=[test_patch],
        )

        # Verify the result
        self.assertEqual(result.commit_sha, commit_sha)
        self.assertTrue(result.success)
        self.assertEqual(result.execution_time, 5.2)
        self.assertTrue(result.patches_applied.get("patch_1", False))

        # Verify the correct methods were called
        self.mock_repo_instance.revparse_single.assert_called_once_with(commit_sha)
        self.mock_repo_instance.checkout_tree.assert_called_once_with(mock_commit)
        self.mock_repo_instance.apply.assert_called_once()
        mock_actions_instance.run_workflow.assert_called_once()

    def test_patch_application_error(self):
        """Test handling of patch application errors."""
        # Set up mocks for the test
        commit_sha = "ghi789"
        test_patch = """diff --git a/test.js b/test.js
--- a/test.js
+++ b/test.js
@@ -1,1 +1,1 @@
-old
+new
"""

        # Mock the repository operations
        mock_commit = mock.MagicMock()
        self.mock_repo_instance.revparse_single.return_value = mock_commit

        # Make the apply method raise a GitError
        import pygit2

        self.mock_repo_instance.apply.side_effect = pygit2.GitError(
            "Patch application failed"
        )

        # Mock the head target to return a commit SHA
        head_target = mock.MagicMock()
        self.mock_repo_instance.head.target = head_target
        head_target.__str__.return_value = commit_sha

        # Execute the test and expect an exception
        with self.assertRaises(PatchApplicationError) as context:
            self.executor.execute_at_commit_with_patches(
                commit_sha=commit_sha,
                patches=[test_patch],
            )

        # Verify the exception details
        self.assertEqual(context.exception.commit_sha, commit_sha)
        self.assertEqual(context.exception.patch_id, "patch_1")  # Now using patch_id
        self.assertIn("Failed to apply patch", context.exception.message)

        # Verify the correct methods were called
        self.mock_repo_instance.revparse_single.assert_called_once_with(commit_sha)
        self.mock_repo_instance.checkout_tree.assert_called_once_with(mock_commit)
        self.mock_repo_instance.apply.assert_called_once()

    def test_execution_timeout(self):
        """Test handling of execution timeouts."""
        # Set up mocks for the test
        commit_sha = "jkl012"

        # Mock the repository operations
        mock_commit = mock.MagicMock()
        self.mock_repo_instance.revparse_single.return_value = mock_commit

        # Set up mock for GitHubActions to raise a TimeoutExpired exception
        mock_actions_instance = mock.MagicMock()
        self.mock_github_actions.return_value = mock_actions_instance

        # Create a mock workflow
        mock_workflow = mock.MagicMock()
        mock_workflow.path = ".github/workflows/test.yml"
        mock_actions_instance.test_workflows = [mock_workflow]

        # Make run_workflow raise a TimeoutExpired exception
        mock_actions_instance.run_workflow.side_effect = subprocess.TimeoutExpired(
            cmd="act",
            timeout=60,
        )

        # Mock the head target to return a commit SHA
        head_target = mock.MagicMock()
        self.mock_repo_instance.head.target = head_target
        head_target.__str__.return_value = commit_sha

        # Execute the test and expect an exception
        with self.assertRaises(ExecutionError) as context:
            self.executor.execute_at_commit(commit_sha)

        # Verify the exception details
        self.assertEqual(context.exception.commit_sha, commit_sha)
        self.assertIn("timed out", context.exception.message.lower())

        # Verify the correct methods were called
        self.mock_repo_instance.revparse_single.assert_called_once_with(commit_sha)
        self.mock_repo_instance.checkout_tree.assert_called_once_with(mock_commit)
        mock_actions_instance.run_workflow.assert_called_once()

    def test_cleanup(self):
        """Test resource cleanup."""
        # Call cleanup
        self.executor.cleanup()

        # Verify the correct methods were called
        self.mock_cache_dir.return_act_cache_dir.assert_called_once_with(
            "/tmp/act_cache"
        )

        # Verify cache_dir was set to None
        self.assertIsNone(self.executor.cache_dir)


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("SKIP_REAL_TESTS", "false").lower() == "true"
    or os.environ.get("CI", "false").lower() == "true",
    reason="Skipping real tests in CI or as per environment variable",
)
def test_real_execution():
    """
    Integration test with a real repository.

    This test will be skipped unless explicitly enabled.
    """
    # Create executor with a real repository
    executor = CommitExecutor(
        repo_url="https://github.com/gitbugactions/gitbugactions-npm-jest-test-repo.git",
        timeout=300,
    )

    try:
        # Get the latest commit
        result = subprocess.run(
            [
                "git",
                "ls-remote",
                "https://github.com/gitbugactions/gitbugactions-npm-jest-test-repo.git",
                "HEAD",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        latest_commit = result.stdout.split()[0]

        # Execute tests at the latest commit
        execution_result = executor.execute_at_commit(latest_commit)

        # Verify execution was successful
        assert execution_result.success
        assert len(execution_result.test_results) > 0
        assert len(execution_result.workflows_executed) > 0

    finally:
        # Clean up resources
        executor.cleanup()


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("SKIP_REAL_TESTS", "false").lower() == "true"
    or os.environ.get("CI", "false").lower() == "true",
    reason="Skipping real tests in CI or as per environment variable",
)
def test_real_execution_with_patch():
    """
    Integration test with a real repository and patch application.

    This test will be skipped unless explicitly enabled.
    It gets two consecutive commits from the repository and applies
    the diff between them as a patch to the first commit.
    """
    # Create executor with a real repository
    repo_url = "https://github.com/gitbugactions/gitbugactions-npm-jest-test-repo.git"
    executor = CommitExecutor(
        repo_url=repo_url,
        timeout=300,
    )

    try:
        # Create a temporary directory to clone the repository for getting commits
        temp_dir = tempfile.mkdtemp(prefix="test_patch_")

        # Clone the repository to get the commit history
        subprocess.run(
            ["git", "clone", repo_url, temp_dir],
            check=True,
            capture_output=True,
        )

        # Get the last two commits
        result = subprocess.run(
            ["git", "log", "--pretty=format:%H", "-n", "2"],
            cwd=temp_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        commits = result.stdout.strip().split("\n")

        if len(commits) < 2:
            pytest.skip("Repository doesn't have at least two commits")

        latest_commit = commits[0]
        previous_commit = commits[1]

        # Generate a patch between the two commits
        result = subprocess.run(
            ["git", "diff", previous_commit, latest_commit],
            cwd=temp_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        patch = result.stdout

        # Clean up the temporary directory
        shutil.rmtree(temp_dir)

        # Execute tests at the previous commit with the patch applied
        # This should make the previous commit behave like the latest commit
        execution_result = executor.execute_at_commit_with_patches(
            commit_sha=previous_commit,
            patches=[patch],
        )

        # Verify execution was successful
        assert execution_result.success
        assert execution_result.passed_count == 5
        assert execution_result.skipped_count == 0
        assert execution_result.failed_count == 0
        assert execution_result.error_count == 0
        assert "patch_1" in execution_result.patches_applied
        assert execution_result.patches_applied["patch_1"] == True

        # Now execute tests at the latest commit without patches
        latest_result = executor.execute_at_commit(latest_commit)

        # Both executions should have similar results
        assert execution_result.success == latest_result.success
        assert len(execution_result.test_results) == len(latest_result.test_results)

        # Compare test results
        passed_count_patched = len(execution_result.passed_tests)
        passed_count_latest = len(latest_result.passed_tests)
        assert (
            passed_count_patched == passed_count_latest
        ), f"Patched commit has {passed_count_patched} passed tests, but latest commit has {passed_count_latest}"

    finally:
        # Clean up resources
        executor.cleanup()

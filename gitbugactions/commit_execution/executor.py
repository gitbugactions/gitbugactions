"""
CommitExecutor class for executing tests at specific commits.
"""

import logging
import os
import subprocess
import tempfile
import uuid
from typing import List, Optional, Union, Dict, Tuple

import pygit2
from unidiff import PatchSet

from gitbugactions.actions.actions import (
    Act,
    ActCacheDirManager,
    ActTestsRun,
    GitHubActions,
)
from gitbugactions.commit_execution.errors import (
    ExecutionError,
    ExecutionTimeoutError,
    PatchApplicationError,
)
from gitbugactions.commit_execution.results import CommitExecutionResult, TestResult
from gitbugactions.utils.repo_utils import clone_repo, delete_repo_clone

logger = logging.getLogger(__name__)


class CommitExecutor:
    """
    Executes tests at specific commits of a Git repository.

    This class provides functionality for:
    - Executing tests at a specific commit
    - Executing tests at a commit with patches applied
    - Managing repository state and resources
    """

    def __init__(
        self,
        repo_url: str,
        work_dir: Optional[str] = None,
        memory_limit: str = "7g",
        timeout: int = 600,
        keep_repo: bool = False,
        offline_mode: bool = False,
        custom_image: Optional[str] = None,
    ):
        """
        Initialize a CommitExecutor.

        Args:
            repo_url: URL of the Git repository to clone
            work_dir: Directory to use for working files (default: temporary directory)
            memory_limit: Memory limit for Docker containers (default: "7g")
            timeout: Timeout for test execution in seconds (default: 600)
            keep_repo: Whether to keep the cloned repository after execution (default: False)
            offline_mode: Whether to run in offline mode (default: False)
            custom_image: Custom Docker image to use (default: None)
        """
        self.repo_url = repo_url
        self.work_dir = work_dir or tempfile.mkdtemp(prefix="commit_executor_")
        self.memory_limit = memory_limit
        self.timeout = timeout
        self.keep_repo = keep_repo
        self.offline_mode = offline_mode
        self.custom_image = custom_image

        # These will be set during initialization
        self.repo_path = None
        self.repo_clone = None
        self.execution_id = str(uuid.uuid4())
        self.cache_dir = ActCacheDirManager.acquire_act_cache_dir()

        # Set memory limit for Act
        Act.set_memory_limit(memory_limit)

        # Initialize the repository
        self._clone_repository()

    def execute_at_commit(
        self, commit_sha: str, workflow_paths: Optional[List[str]] = None
    ) -> CommitExecutionResult:
        """
        Execute tests at a specific commit.

        Args:
            commit_sha: SHA of the commit to execute tests at
            workflow_paths: Optional list of specific workflow paths to execute

        Returns:
            CommitExecutionResult containing the results of the execution

        Raises:
            ExecutionError: If there is an error during execution
            ExecutionTimeoutError: If execution times out
        """
        logger.info(f"Executing tests at commit {commit_sha}")

        try:
            # Checkout the commit
            self._checkout_commit(commit_sha)

            # Get workflow information
            all_workflows, test_workflows, all_build_tools, test_build_tools = self._get_workflow_info()

            # Execute workflows
            act_results = self._execute_workflows(workflow_paths)

            # Convert results
            result = self._convert_act_results(act_results)
            result.commit_sha = commit_sha

            # Add workflow information
            result.all_workflows = all_workflows
            result.test_workflows = test_workflows
            result.all_build_tools = all_build_tools
            result.test_build_tools = test_build_tools

            return result

        except subprocess.TimeoutExpired as e:
            raise ExecutionTimeoutError(
                message=f"Execution timed out after {self.timeout} seconds",
                commit_sha=commit_sha,
                timeout=self.timeout,
                running_workflows=workflow_paths or [],
            )
        except Exception as e:
            raise ExecutionError(
                message=f"Error executing tests at commit {commit_sha}: {str(e)}",
                commit_sha=commit_sha,
                is_infrastructure_error=True,
                stdout=getattr(e, "stdout", None),
                stderr=getattr(e, "stderr", None),
            )
        finally:
            # Clean up the repository state but keep the clone
            self._clean_repository()

    def execute_at_commit_with_patches(
        self,
        commit_sha: str,
        patches: Optional[List[Union[PatchSet, str]]] = None,
        workflow_paths: Optional[List[str]] = None,
    ) -> CommitExecutionResult:
        """
        Execute tests at a commit after applying specified patches.
        
        Args:
            commit_sha: SHA of the commit to execute tests at
            patches: Optional list of patches to apply
            workflow_paths: Optional list of specific workflow paths to execute
            
        Returns:
            CommitExecutionResult containing the results of the execution
            
        Raises:
            PatchApplicationError: If patches cannot be applied cleanly
            ExecutionError: If there is an error during execution
            ExecutionTimeoutError: If execution times out
        """
        logger.info(f"Executing tests at commit {commit_sha} with patches")
        
        try:
            # Checkout the commit
            self._checkout_commit(commit_sha)
            
            # Apply patches
            patches_applied = {}
            
            if patches:
                for i, patch in enumerate(patches):
                    patch_id = f"patch_{i+1}"
                    logger.debug(f"Applying {patch_id}")
                    patches_applied[patch_id] = self._apply_patch(patch, patch_id)
            
            # Get workflow information
            all_workflows, test_workflows, all_build_tools, test_build_tools = self._get_workflow_info()
            
            # Execute workflows
            act_results = self._execute_workflows(workflow_paths)
            
            # Convert results
            result = self._convert_act_results(act_results)
            result.commit_sha = commit_sha
            result.patches_applied = patches_applied
            
            # Add workflow information
            result.all_workflows = all_workflows
            result.test_workflows = test_workflows
            result.all_build_tools = all_build_tools
            result.test_build_tools = test_build_tools
            
            return result
            
        except subprocess.TimeoutExpired as e:
            raise ExecutionTimeoutError(
                message=f"Execution timed out after {self.timeout} seconds",
                commit_sha=commit_sha,
                timeout=self.timeout,
                running_workflows=workflow_paths or [],
            )
        except Exception as e:
            if isinstance(e, PatchApplicationError):
                raise e
            raise ExecutionError(
                message=f"Error executing tests at commit {commit_sha} with patches: {str(e)}",
                commit_sha=commit_sha,
                is_infrastructure_error=True,
                stdout=getattr(e, "stdout", None),
                stderr=getattr(e, "stderr", None),
            )
        finally:
            # Clean up the repository state but keep the clone
            self._clean_repository()

    def get_workflow_info_at_commit(self, commit_sha: str) -> Dict[str, List[str]]:
        """
        Get information about workflows at a specific commit without executing tests.

        Args:
            commit_sha: SHA of the commit to get workflow information for

        Returns:
            Dictionary containing lists of all workflows, test workflows, and build tools

        Raises:
            ExecutionError: If there is an error during execution
        """
        logger.info(f"Getting workflow information at commit {commit_sha}")

        try:
            # Checkout the commit
            self._checkout_commit(commit_sha)

            # Get workflow information
            all_workflows, test_workflows, all_build_tools, test_build_tools = self._get_workflow_info()

            return {
                "all_workflows": all_workflows,
                "test_workflows": test_workflows,
                "all_build_tools": all_build_tools,
                "test_build_tools": test_build_tools
            }

        except Exception as e:
            raise ExecutionError(
                message=f"Error getting workflow information at commit {commit_sha}: {str(e)}",
                commit_sha=commit_sha,
                is_infrastructure_error=True,
            )
        finally:
            # Clean up the repository state but keep the clone
            self._clean_repository()

    def cleanup(self) -> None:
        """
        Clean up resources used by the executor.

        This includes:
        - Returning cache directories
        - Removing cloned repositories if not kept
        """
        logger.info("Cleaning up resources")

        # Return the cache directory
        if self.cache_dir:
            ActCacheDirManager.return_act_cache_dir(self.cache_dir)
            self.cache_dir = None

        # Delete the repository if not keeping it
        if self.repo_clone and not self.keep_repo:
            delete_repo_clone(self.repo_clone)
            self.repo_clone = None
            self.repo_path = None

    def _clone_repository(self) -> None:
        """
        Clone the repository to the working directory.

        Raises:
            ExecutionError: If there is an error cloning the repository
        """
        logger.info(f"Cloning repository {self.repo_url}")

        try:
            # Create a unique directory for this repository
            repo_dir = os.path.join(self.work_dir, f"repo_{self.execution_id}")
            os.makedirs(repo_dir, exist_ok=True)

            # Clone the repository
            self.repo_clone = clone_repo(self.repo_url, repo_dir)
            self.repo_path = repo_dir

            # Set gc.auto to 0 to avoid "too many open files" bug
            subprocess.run(
                "git config gc.auto 0",
                cwd=self.repo_path,
                shell=True,
                capture_output=True,
                check=True,
            )

            logger.debug(f"Repository cloned to {self.repo_path}")

        except Exception as e:
            raise ExecutionError(
                message=f"Error cloning repository {self.repo_url}: {str(e)}",
                commit_sha="",
                is_infrastructure_error=True,
            )

    def _checkout_commit(self, commit_sha: str) -> None:
        """
        Check out a specific commit.

        Args:
            commit_sha: SHA of the commit to check out

        Raises:
            ExecutionError: If there is an error checking out the commit
        """
        logger.info(f"Checking out commit {commit_sha}")

        try:
            # Get the commit object
            commit = self.repo_clone.revparse_single(commit_sha)

            # Clean the repository
            self._clean_repository()

            # Checkout the commit
            self.repo_clone.checkout_tree(commit)
            self.repo_clone.set_head(commit.id)

            logger.debug(f"Checked out commit {commit_sha}")

        except Exception as e:
            raise ExecutionError(
                message=f"Error checking out commit {commit_sha}: {str(e)}",
                commit_sha=commit_sha,
                is_infrastructure_error=True,
            )

    def _clean_repository(self) -> None:
        """
        Clean the repository to ensure a clean state.
        """
        # Run git clean to remove untracked files
        subprocess.run(
            ["git", "clean", "-ffdx"],
            cwd=self.repo_path,
            capture_output=True,
            check=True,
        )

        # Reset any changes
        head = self.repo_clone.head.target
        self.repo_clone.reset(head, pygit2.GIT_RESET_HARD)

    def _apply_patch(self, patch: Union[PatchSet, str], patch_id: str) -> bool:
        """
        Apply a patch to the current repository state.

        Args:
            patch: Patch to apply (either a PatchSet object or a string)
            patch_id: Identifier for the patch (for logging and error reporting)

        Returns:
            Whether the patch was successfully applied

        Raises:
            PatchApplicationError: If the patch cannot be applied cleanly
        """
        logger.info(f"Applying patch {patch_id}")

        # Convert string to PatchSet if needed
        if isinstance(patch, str):
            patch = PatchSet(patch)

        # Clean the patch to avoid libgit2 segfaults
        patch = self._clean_patch(patch)

        try:
            # Apply the patch
            self.repo_clone.apply(pygit2.Diff.parse_diff(str(patch)))
            return True

        except pygit2.GitError as e:
            # Get the current commit SHA
            commit_sha = str(self.repo_clone.head.target)

            # Get the list of files that failed to apply
            failed_files = []
            for file in patch:
                failed_files.append(file.target_file)

            raise PatchApplicationError(
                message=f"Failed to apply patch {patch_id} to commit {commit_sha}: {str(e)}",
                commit_sha=commit_sha,
                failed_files=failed_files,
                patch_type=patch_id,
                original_patch=str(patch),
            )

    def _clean_patch(self, patch: PatchSet) -> PatchSet:
        """
        Cleans the patch to be used by pygit2.
        This is related to an issue that causes libgit2 to segfault when one of the paths is /dev/null.
        """
        for file in patch:
            if file.source_file == "/dev/null" and not file.is_added_file:
                file.source_file = file.target_file.replace("b/", "a/", 1)
            elif file.target_file == "/dev/null" and not file.is_removed_file:
                file.target_file = file.source_file.replace("a/", "b/", 1)
        return patch

    def _detect_language(self) -> str:
        """
        Detect the primary programming language of the repository.

        Returns:
            Detected language or "unknown" if no recognizable files are found
        """
        logger.info("Detecting repository language")

        # Check for common language files
        language_extensions = {
            "js": "javascript",
            "ts": "typescript",
            "jsx": "javascript",
            "tsx": "typescript",
            "py": "python",
            "java": "java",
            "rb": "ruby",
            "go": "go",
            "php": "php",
            "cs": "csharp",
            "cpp": "cpp",
            "c": "c",
            "rs": "rust",
        }

        extension_counts = {}

        # Walk through the repository and count file extensions
        for root, _, files in os.walk(self.repo_path):
            # Skip .git directory
            if ".git" in root:
                continue

            for file in files:
                ext = file.split(".")[-1].lower() if "." in file else ""
                if ext in language_extensions:
                    extension_counts[ext] = extension_counts.get(ext, 0) + 1

        # Find the most common extension
        if extension_counts:
            most_common_ext = max(extension_counts, key=extension_counts.get)
            language = language_extensions[most_common_ext]
            logger.debug(f"Detected language: {language}")
            return language

        logger.debug("Could not detect language, using 'unknown'")
        return "unknown"

    def _execute_workflows(
        self, workflow_paths: Optional[List[str]] = None
    ) -> List[ActTestsRun]:
        """
        Execute GitHub Actions workflows.

        Args:
            workflow_paths: Optional list of specific workflow paths to execute

        Returns:
            List of ActTestsRun objects containing the results

        Raises:
            ExecutionError: If there is an error during execution
            ExecutionTimeoutError: If execution times out
        """
        logger.info("Executing workflows")

        try:
            # Detect language
            language = self._detect_language()

            # Initialize GitHub Actions
            actions = GitHubActions(
                self.repo_path,
                language,
                keep_containers=False,
                runner_image=self.custom_image or "gitbugactions:latest",
                offline=self.offline_mode,
            )

            # Filter workflows if paths are specified
            if workflow_paths:
                filtered_workflows = []
                for workflow in actions.test_workflows:
                    if any(path in workflow.path for path in workflow_paths):
                        filtered_workflows.append(workflow)
                actions.test_workflows = filtered_workflows

            # If no test workflows found, return empty result
            if not actions.test_workflows:
                logger.warning("No test workflows found")
                return []

            # Randomize workflow names to avoid conflicts
            for workflow in actions.test_workflows:
                workflow.doc["name"] = str(uuid.uuid4())

            # Save workflows
            actions.save_workflows()

            # Execute workflows
            act_runs = []
            for workflow in actions.test_workflows:
                act_run = actions.run_workflow(
                    workflow,
                    self.cache_dir,
                    timeout=self.timeout // 60,  # Convert seconds to minutes
                )
                act_runs.append(act_run)

            # Delete workflows
            actions.delete_workflows()

            return act_runs

        except Exception as e:
            if isinstance(e, subprocess.TimeoutExpired):
                raise ExecutionTimeoutError(
                    message=f"Execution timed out after {self.timeout} seconds",
                    commit_sha=str(self.repo_clone.head.target),
                    timeout=self.timeout,
                    running_workflows=workflow_paths or [],
                )
            raise ExecutionError(
                message=f"Error executing workflows: {str(e)}",
                commit_sha=str(self.repo_clone.head.target),
                is_infrastructure_error=True,
                stdout=getattr(e, "stdout", None),
                stderr=getattr(e, "stderr", None),
            )

    def _convert_act_results(
        self, act_results: List[ActTestsRun]
    ) -> CommitExecutionResult:
        """
        Convert ActTestsRun results to a CommitExecutionResult.

        Args:
            act_results: List of ActTestsRun objects

        Returns:
            CommitExecutionResult containing the converted results
        """
        logger.info("Converting execution results")

        # Create a new CommitExecutionResult
        result = CommitExecutionResult(
            commit_sha=str(self.repo_clone.head.target),
            success=True,
            execution_time=0.0,
            workflows_executed=[],
        )

        # If no results, return empty result
        if not act_results:
            return result

        # Process each ActTestsRun
        for act_run in act_results:
            # Add workflow to executed list
            result.workflows_executed.append(act_run.workflow.path)

            # Add execution time
            result.execution_time += act_run.elapsed_time

            # If any run failed, mark the result as failed
            if act_run.failed:
                result.success = False

            # Add stdout/stderr
            if act_run.stdout:
                result.stdout = (result.stdout or "") + act_run.stdout
            if act_run.stderr:
                result.stderr = (result.stderr or "") + act_run.stderr

            # Convert test results
            for test in act_run.tests:
                # Determine test result
                if test.is_passed:
                    result_str = "passed"
                elif test.is_skipped:
                    result_str = "skipped"
                elif test.is_error:
                    result_str = "error"
                else:
                    result_str = "failed"

                # Create TestResult object
                test_result = TestResult(
                    name=test.name,
                    classname=test.classname,
                    result=result_str,
                    message=test.message if hasattr(test, "message") else None,
                    time=test.time,
                    stdout=test.system_out,
                    stderr=test.system_err,
                )

                # Add to results
                result.test_results.append(test_result)

        return result

    def _get_workflow_info(self) -> Tuple[List[str], List[str], List[str], List[str]]:
        """
        Get information about all workflows and test workflows in the repository.
        
        Returns:
            Tuple containing lists of all workflows, test workflows, all build tools, and test build tools
        """
        logger.info("Getting workflow information")
        
        try:
            # Detect language
            language = self._detect_language()
            
            # Initialize GitHub Actions
            actions = GitHubActions(
                self.repo_path,
                language,
                keep_containers=False,
                runner_image=self.custom_image or "gitbugactions:latest",
                offline=self.offline_mode,
            )
            
            # Get workflow information
            all_workflows = [workflow.path for workflow in actions.workflows]
            test_workflows = [workflow.path for workflow in actions.test_workflows]
            
            # Get build tools information if available
            all_build_tools = []
            test_build_tools = []
            
            for workflow in actions.workflows:
                if hasattr(workflow, 'get_build_tool'):
                    build_tool = workflow.get_build_tool()
                    if build_tool:
                        all_build_tools.append(build_tool)
            
            for workflow in actions.test_workflows:
                if hasattr(workflow, 'get_build_tool'):
                    build_tool = workflow.get_build_tool()
                    if build_tool:
                        test_build_tools.append(build_tool)
            
            return all_workflows, test_workflows, all_build_tools, test_build_tools
            
        except Exception as e:
            logger.error(f"Error getting workflow information: {str(e)}")
            return [], [], [], []

    def __del__(self):
        """
        Destructor to ensure resources are cleaned up.
        """
        try:
            self.cleanup()
        except Exception as e:
            logger.warning(f"Error during cleanup in destructor: {e}")

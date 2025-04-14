from typing import Dict, List, Optional, Set, Tuple
from junitparser import TestCase
from pathlib import Path
import re
import logging
import os

from gitbugactions.actions.workflow import GitHubWorkflow
from gitbugactions.actions.multi.junitxmlparser import JUnitXMLParser
from gitbugactions.actions.csharp.helpers.dotnet_project_analyzer import (
    DotNetProjectAnalyzer,
)

logger = logging.getLogger(__name__)


class DotNetWorkflow(GitHubWorkflow):
    BUILD_TOOL_KEYWORDS = {"dotnet", "vstest"}
    # Regex patterns to match .NET test commands
    __TESTS_COMMAND_PATTERNS = [
        r"dotnet\s+test",
    ]

    def __init__(self, path: str, workflow: str = ""):
        super().__init__(path, workflow)
        self.source_dirs = None
        self.test_dirs = None
        self.analyzer = None

        # Extract owner/name from path
        if "/" in path:
            self.owner, self.name = path.split("/", 1)
        else:
            self.owner = ""
            self.name = path

    def _is_test_command(self, command) -> bool:
        # Checks if the given command matches any of the tests command patterns
        for pattern in DotNetWorkflow.__TESTS_COMMAND_PATTERNS:
            if re.search(pattern, command):
                return True
        return False

    def instrument_test_steps(self, **kwargs):
        """
        Instrument the test steps to capture test results.

        Args:
            repo_clone: Optional path to the repository clone, used for determining project structure
        """
        if "repo_clone" not in kwargs:
            logger.warning("No repo clone provided, skipping test instrumentation")
            return
        repo_clone = kwargs["repo_clone"]

        # Add reporting options to the test command
        test_step_indices = []
        if "jobs" in self.doc:
            for job_name, job in self.doc["jobs"].items():
                if "steps" in job:
                    for step in job["steps"]:
                        if "run" in step and self._is_test_command(step["run"]):
                            test_step_indices.append(
                                (job_name, job["steps"].index(step))
                            )

        if len(test_step_indices) == 0:
            logger.warning("No test steps detected, skipping test instrumentation")
            return

        self.set_project_structure(repo_clone)
        logger.info(f"Detected source directories: {self.source_dirs}")
        logger.info(f"Detected test directories: {self.test_dirs}")

        # Instrument the test directories
        for test_dir in self.test_dirs:
            # Add the test logger to the test directory
            self.doc["jobs"][test_step_indices[0][0]]["steps"].insert(
                test_step_indices[0][1],
                {
                    "name": f"Add test logger to {test_dir}",
                    "run": (
                        f"cd {test_dir} && "
                        f"dotnet add package JUnitXml.TestLogger --version 5.0.0 && "
                        f"dotnet build && cd .."
                    ),
                },
            )

            # Update the indices to account for the new step
            test_step_indices = [
                (job_name, step_index + 1) for job_name, step_index in test_step_indices
            ]

        # Instrument the test steps
        for test_step_index in test_step_indices:
            # Modify the original test command to use the logger
            original_command = self.doc["jobs"][test_step_index[0]]["steps"][
                test_step_index[1]
            ]["run"]
            self.doc["jobs"][test_step_index[0]]["steps"][test_step_index[1]]["run"] = (
                f"{original_command.strip()} "
                f'--logger:"junit;LogFilePath=TestResults/test-results.xml"'
            )

    def instrument_offline_execution(self):
        pass

    def get_test_results(self, repo_path) -> List[TestCase]:
        self.set_project_structure(repo_path, no_ignore=True)
        if self.test_dirs is None:
            raise ValueError(f"Test directories not found in {self.path}")

        parser = JUnitXMLParser()

        # If we have identified test directories, look for test results there
        test_results = []
        for test_dir in self.test_dirs:
            results_path = str(Path(repo_path, test_dir, "TestResults"))
            test_results.extend(parser.get_test_results(results_path))

        return test_results

    def get_build_tool(self) -> str:
        return "dotnet"

    def set_project_structure(self, repo_path, no_ignore=False) -> None:
        """
        Analyze repository structure to identify source and test directories.
        Sets the source_dirs and test_dirs attributes.

        Args:
            repo_path: Path to the repository root

        Returns:
            Tuple[Set[str], Set[str]]: Sets of source and test directory paths
        """
        if self.source_dirs is not None and self.test_dirs is not None:
            return self.source_dirs, self.test_dirs

        try:
            # Create analyzer if not exists
            if self.analyzer is None:
                self.analyzer = DotNetProjectAnalyzer(repo_path, no_ignore)

            # Analyze repository structure
            self.source_dirs, self.test_dirs = self.analyzer.analyze_repository()

            logger.info(f"Identified source directories: {self.source_dirs}")
            logger.info(f"Identified test directories: {self.test_dirs}")
        except Exception as e:
            logger.error(f"Error analyzing .NET project structure: {e}")
            # Return reasonable defaults on error
            self.source_dirs = {"src", "."}
            self.test_dirs = {"test", "tests"}

    def get_source_directories(self, repo_path) -> Set[str]:
        """
        Get source code directories from the repository.

        Args:
            repo_path: Path to the repository root

        Returns:
            Set[str]: Set of source directory paths
        """
        self.set_project_structure(repo_path)
        return self.source_dirs

    def get_test_directories(self, repo_path) -> Set[str]:
        """
        Get test directories from the repository.

        Args:
            repo_path: Path to the repository root

        Returns:
            Set[str]: Set of test directory paths
        """
        self.set_project_structure(repo_path)
        return self.test_dirs

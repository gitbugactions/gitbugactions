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

    def instrument_test_steps(self, repo_clone: Optional[str] = None):
        """
        Instrument the test steps to capture test results.

        Args:
            repo_clone: Optional path to the repository clone, used for determining project structure
        """
        # Add reporting options to the test command
        if "jobs" in self.doc:
            for _, job in self.doc["jobs"].items():
                if "steps" in job:
                    for step in job["steps"]:
                        if "run" in step and self._is_test_command(step["run"]):
                            # If we have access to GitHub API, try to analyze project structure first
                            if (
                                repo_clone
                                and not self.source_dirs
                                and not self.test_dirs
                            ):
                                try:
                                    self.get_project_structure(repo_clone)
                                    logger.info(
                                        f"Detected source directories: {self.source_dirs}"
                                    )
                                    logger.info(
                                        f"Detected test directories: {self.test_dirs}"
                                    )

                                    # TODO: Handle multiple test directories
                                    if len(self.test_dirs) == 1:
                                        test_dir = list(self.test_dirs)[0]
                                        # Modify the original command to include the logger option
                                        # but don't change directory
                                        original_command = step["run"]

                                        # Create a multi-step command that:
                                        # 1. Adds the JUnitXml.TestLogger package to the test project
                                        # 2. Builds the project to ensure the package is properly integrated
                                        # 3. Runs the original test command with the logger option
                                        step["run"] = (
                                            f"cd {test_dir} && dotnet add package JUnitXml.TestLogger --version 5.0.0 && "
                                            f"dotnet build && cd .. && {original_command} "
                                            f'--logger:"junit;LogFilePath=TestResults/test-results.xml"'
                                        )
                                    elif (
                                        len(self.source_dirs) == 0
                                        or len(self.test_dirs) == 0
                                    ):
                                        logger.warning(
                                            "Cannot instrument test steps, no source or test directories detected"
                                        )
                                    else:
                                        logger.warning(
                                            "Cannot instrument test steps, multiple test directories detected"
                                        )

                                except Exception as e:
                                    logger.warning(
                                        f"Error analyzing .NET project structure: {e}"
                                    )
                            else:
                                logger.warning(
                                    "No repo clone provided, cannot instrument .NET test steps"
                                )

    def instrument_offline_execution(self):
        pass

    def get_test_results(self, repo_path) -> List[TestCase]:
        parser = JUnitXMLParser()

        # If we have identified test directories, look for test results there
        if self.test_dirs and len(self.test_dirs) == 1:
            test_dir = list(self.test_dirs)[0]
            results_path = str(Path(repo_path, test_dir, "TestResults"))
            return parser.get_test_results(results_path)

        # Fallback to the original behavior if test directories are not identified
        return parser.get_test_results(str(Path(repo_path, "TestResults")))

    def get_build_tool(self) -> str:
        return "dotnet"

    def get_project_structure(self, repo_path) -> Tuple[Set[str], Set[str]]:
        """
        Analyze repository structure to identify source and test directories.

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
                self.analyzer = DotNetProjectAnalyzer(repo_path)

            # Analyze repository structure
            self.source_dirs, self.test_dirs = self.analyzer.analyze_repository()

            logger.info(f"Identified source directories: {self.source_dirs}")
            logger.info(f"Identified test directories: {self.test_dirs}")

            return self.source_dirs, self.test_dirs
        except Exception as e:
            logger.error(f"Error analyzing .NET project structure: {e}")
            # Return reasonable defaults on error
            self.source_dirs = {"src", "."}
            self.test_dirs = {"test", "tests"}
            return self.source_dirs, self.test_dirs

    def get_source_directories(self, repo_path) -> Set[str]:
        """
        Get source code directories from the repository.

        Args:
            repo_path: Path to the repository root

        Returns:
            Set[str]: Set of source directory paths
        """
        source_dirs, _ = self.get_project_structure(repo_path)
        return source_dirs

    def get_test_directories(self, repo_path) -> Set[str]:
        """
        Get test directories from the repository.

        Args:
            repo_path: Path to the repository root

        Returns:
            Set[str]: Set of test directory paths
        """
        _, test_dirs = self.get_project_structure(repo_path)
        return test_dirs

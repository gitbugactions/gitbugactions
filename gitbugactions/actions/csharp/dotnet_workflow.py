from typing import Dict, List, Optional, Set, Tuple
from junitparser import TestCase
from pathlib import Path
import re
import logging

from gitbugactions.actions.workflow import GitHubWorkflow
from gitbugactions.actions.multi.junitxmlparser import JUnitXMLParser
from gitbugactions.actions.csharp.helpers import DotNetProjectAnalyzer

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

    def instrument_test_steps(self, github_api=None):
        """
        Instrument the test steps to capture test results.

        Args:
            github_api: Optional GitHub API instance, used for determining project structure
        """
        # Add reporting options to the test command
        if "jobs" in self.doc:
            for _, job in self.doc["jobs"].items():
                if "steps" in job:
                    for step in job["steps"]:
                        if "run" in step and self._is_test_command(step["run"]):
                            # If we have access to GitHub API, try to analyze project structure first
                            if (
                                github_api
                                and not self.source_dirs
                                and not self.test_dirs
                            ):
                                try:
                                    self.get_project_structure(github_api)
                                    logger.info(
                                        f"Detected source directories: {self.source_dirs}"
                                    )
                                    logger.info(
                                        f"Detected test directories: {self.test_dirs}"
                                    )

                                    print(self.source_dirs)
                                    print(self.test_dirs)
                                    if (
                                        len(self.source_dirs) == 1
                                        and len(self.test_dirs) == 1
                                    ):
                                        step["run"] = (
                                            f'cd {self.source_dirs} && dotnet add package JUnitXml.TestLogger --version 5.0.0 && {step["run"]} --logger:"junit;LogFilePath=./TestResults/test-results.xml"'
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
                                            "Cannot instrument test steps, multiple source or test directories detected"
                                        )

                                except Exception as e:
                                    logger.warning(
                                        f"Error analyzing .NET project structure: {e}"
                                    )
                            else:
                                logger.warning(
                                    "No GitHub API available, cannot instrument test steps"
                                )

    def instrument_offline_execution(self):
        pass

    def get_test_results(self, repo_path) -> List[TestCase]:
        parser = JUnitXMLParser()
        return parser.get_test_results(str(Path(repo_path, "TestResults")))

    def get_build_tool(self) -> str:
        return "dotnet"

    def get_project_structure(self, github_api) -> Tuple[Set[str], Set[str]]:
        """
        Analyze repository structure to identify source and test directories without cloning.

        Args:
            github_api: Instance of GithubAPI

        Returns:
            Tuple[Set[str], Set[str]]: Sets of source and test directory paths
        """
        if self.source_dirs is not None and self.test_dirs is not None:
            return self.source_dirs, self.test_dirs

        try:
            # Create analyzer if not exists
            if self.analyzer is None:
                self.analyzer = DotNetProjectAnalyzer(github_api)

            # Analyze repository structure
            repo_name = self.path  # path should already be in format "owner/repo"
            self.source_dirs, self.test_dirs = self.analyzer.analyze_repository(
                repo_name
            )

            logger.info(f"Identified source directories: {self.source_dirs}")
            logger.info(f"Identified test directories: {self.test_dirs}")

            # Handle edge cases where analysis didn't yield results
            if not self.source_dirs and not self.test_dirs:
                # If we couldn't find any directories, use reasonable defaults
                self.source_dirs = {"src", "."}
                self.test_dirs = {"test", "tests"}
                logger.warning("Using default source and test directories")

            return self.source_dirs, self.test_dirs
        except Exception as e:
            logger.error(f"Error analyzing .NET project structure: {e}")
            # Return reasonable defaults on error
            return {"src", "."}, {"test", "tests"}

    def get_source_directories(self, github_api) -> Set[str]:
        """
        Get source code directories from the repository.

        Args:
            github_api: Instance of GithubAPI

        Returns:
            Set[str]: Set of source directory paths
        """
        source_dirs, _ = self.get_project_structure(github_api)
        return source_dirs

    def get_test_directories(self, github_api) -> Set[str]:
        """
        Get test directories from the repository.

        Args:
            github_api: Instance of GithubAPI

        Returns:
            Set[str]: Set of test directory paths
        """
        _, test_dirs = self.get_project_structure(github_api)
        return test_dirs

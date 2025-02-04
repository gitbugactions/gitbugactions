from typing import List
from junitparser import TestCase
from pathlib import Path
import re

from gitbugactions.actions.workflow import GitHubWorkflow
from gitbugactions.actions.multi.junitxmlparser import JUnitXMLParser


class DotNetWorkflow(GitHubWorkflow):
    BUILD_TOOL_KEYWORDS = {"dotnet", "vstest"}
    # Regex patterns to match .NET test commands
    __TESTS_COMMAND_PATTERNS = [
        r"dotnet\s+test",
    ]

    def _is_test_command(self, command) -> bool:
        # Checks if the given command matches any of the tests command patterns
        for pattern in DotNetWorkflow.__TESTS_COMMAND_PATTERNS:
            if re.search(pattern, command):
                return True
        return False

    def instrument_test_steps(self):
        # Add reporting options to the test command
        if "jobs" in self.doc:
            for _, job in self.doc["jobs"].items():
                if "steps" in job:
                    for step in job["steps"]:
                        if "run" in step and self._is_test_command(step["run"]):
                            step["run"] = (
                                f'dotnet add package JUnitXml.TestLogger && {step["run"]} --logger:"junit;LogFilePath=./TestResults/test-results.xml"'
                            )

    def instrument_offline_execution(self):
        pass

    def get_test_results(self, repo_path) -> List[TestCase]:
        parser = JUnitXMLParser()
        return parser.get_test_results(str(Path(repo_path, "TestResults")))

    def get_build_tool(self) -> str:
        return "dotnet"

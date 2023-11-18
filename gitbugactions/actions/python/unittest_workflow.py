from typing import List
from junitparser import TestCase
from pathlib import Path
import re

from gitbugactions.actions.workflow import GitHubWorkflow
from gitbugactions.actions.multi.junitxmlparser import JUnitXMLParser


class UnittestWorkflow(GitHubWorkflow):
    BUILD_TOOL_KEYWORDS = ["unittest", "xmlrunner"]
    # Regex patterns to match unittest commands
    __TESTS_COMMAND_PATTERNS = [
        r"python([23](\.\d+)?)?\s+(([^\s]+\s+)*)?-m\s+unittest",  # Matches commands that call unittest through python's module option
        r"python([23](\.\d+)?)?\s+(([^\s]+\s+)*)?-m\s+xmlrunner",  # Matches commands that call xlmrunner through python's module option
    ]

    def _is_test_command(self, command) -> bool:
        # Checks if the given command matches any of the tests command patterns
        for pattern in UnittestWorkflow.__TESTS_COMMAND_PATTERNS:
            if re.search(pattern, command):
                return True
        return False

    def instrument_test_steps(self):
        if "jobs" in self.doc:
            for _, job in self.doc["jobs"].items():
                if "steps" in job:
                    for step in job["steps"]:
                        if "run" in step and self._is_test_command(step["run"]):
                            # We need to install the xmlrunner package to generate the reports
                            new_step_run = "pip install unittest-xml-reporting && "
                            if "-m unittest" in step["run"]:
                                # Replace the unittest command with the xmlrunner command
                                new_step_run += step["run"].replace(
                                    "-m unittest", "-m xmlrunner -o ./test_reports"
                                )
                            elif (
                                "-m xmlrunner" in step["run"]
                                and "-o" not in step["run"]
                            ):
                                # Add the output folder to the xmlrunner command
                                new_step_run += step["run"].replace(
                                    "-m xmlrunner", "-m xmlrunner -o ./test_reports"
                                )
                            elif "-m xmlrunner" in step["run"] and "-o" in step["run"]:
                                # Replace the output folder with the test_reports folder
                                new_step_run += re.sub(
                                    r"-o [^\s]+", "-o ./test_reports", step["run"]
                                )
                            else:
                                # We don't know how to instrument this command
                                new_step_run += step["run"]
                            step["run"] = new_step_run

    def get_test_results(self, repo_path) -> List[TestCase]:
        parser = JUnitXMLParser()
        return parser.get_test_results(str(Path(repo_path, "test_reports")))

    def get_build_tool(self) -> str:
        return "unittest"

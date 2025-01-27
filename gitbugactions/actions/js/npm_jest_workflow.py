from typing import List
from junitparser import TestCase
from pathlib import Path
import re

from gitbugactions.actions.workflow import GitHubWorkflow
from gitbugactions.actions.multi.junitxmlparser import JUnitXMLParser


class NpmJestWorkflow(GitHubWorkflow):
    BUILD_TOOL_KEYWORDS = ["npm"]
    # Regex patterns to match maven test commands
    __TESTS_COMMAND_PATTERN = r"npm\s+test\b"

    def _is_test_command(self, command) -> bool:
        return bool(re.search(self.__TESTS_COMMAND_PATTERN, command))

    def instrument_test_steps(self):
        if "jobs" in self.doc:
            for _, job in self.doc["jobs"].items():
                if "steps" in job:
                    for step in job["steps"]:
                        if "run" in step and self._is_test_command(step["run"]):
                            step[
                                "run"
                            ] = f"""npm install --save-dev jest-junit
{step['run']} -- --reporters=default --reporters=jest-junit"""

    def get_test_results(self, repo_path) -> List[TestCase]:
        parser = JUnitXMLParser()
        # Jest-junit outputs to junit.xml by default
        return parser.get_test_results(str(Path(repo_path, "junit.xml")))

    def get_build_tool(self) -> str:
        return "npm"

import re, os, glob
from typing import List

from junitparser import TestCase, Error

from gitbugactions.actions.multi.junitxmlparser import JUnitXMLParser
from gitbugactions.actions.workflow import GitHubWorkflow


class CMakeWorkflow(GitHubWorkflow):
    BUILD_TOOL_KEYWORDS = {"cmake"}
    __TESTS_COMMAND_PATTERNS = [
        r"ctest",
    ]
    result_file = "report.xml"

    def _is_test_command(self, command) -> bool:
        # Checks if the given command matches any of the tests command patterns
        for pattern in CMakeWorkflow.__TESTS_COMMAND_PATTERNS:
            if re.search(pattern, command):
                return True
        return False

    def instrument_test_steps(self):
        if "jobs" in self.doc:
            for _, job in self.doc["jobs"].items():
                if "steps" in job:
                    for step in job["steps"]:
                        if "run" in step and self._is_test_command(step["run"]):
                            if "--output-junit" in step["run"]:
                                m = re.search(r"--output-junit\s+(\S+)", step["run"])
                                if m:
                                    self.result_file = m.group(1)
                            else:
                                step["run"] = step["run"].replace(
                                    "ctest", "ctest --output-junit " + self.result_file
                                )

    def get_test_results(self, repo_path) -> List[TestCase]:
        search_path = os.path.join(repo_path, '**', self.result_file)
        files = glob.glob(search_path, recursive=True)
        if files:
            parser = JUnitXMLParser()
            return parser.get_test_results(files[0])
        else:
            test_case = TestCase(name="NoTestResult", classname="CMakeWorkflow")
            test_case.result = Error('No test results found')
            return [test_case]

    def get_build_tool(self) -> str:
        return "cmake"

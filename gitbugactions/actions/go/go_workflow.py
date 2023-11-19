from typing import List
from junitparser import TestCase
from pathlib import Path
import re

from gitbugactions.actions.workflow import GitHubWorkflow
from gitbugactions.actions.multi.junitxmlparser import JUnitXMLParser


class GoWorkflow(GitHubWorkflow):
    BUILD_TOOL_KEYWORDS = ["go"]
    # Regex patterns to match go test commands
    __TESTS_COMMAND_PATTERNS = [
        r"go\s+(([^\s]+\s+)*)?test",
    ]

    def _is_test_command(self, command) -> bool:
        # Checks if the given command matches any of the tests command patterns
        for pattern in GoWorkflow.__TESTS_COMMAND_PATTERNS:
            if re.search(pattern, command):
                return True
        return False

    def instrument_test_steps(self):
        if "jobs" in self.doc:
            for _, job in self.doc["jobs"].items():
                if "steps" in job:
                    for step in job["steps"]:
                        if "run" in step and self._is_test_command(step["run"]):
                            # We need to install the go-test-report package to generate the reports
                            new_step_run = "go install github.com/jstemmer/go-junit-report/v2@v2.0.0 && "
                            if "-v" not in step["run"]:
                                step["run"] = re.sub(
                                    r"test",
                                    "test -v",
                                    step["run"],
                                )
                            if "go-junit-report" in step["run"] and ">" in step["run"]:
                                step["run"] = re.sub(
                                    r"> [^\s]+",
                                    "report.xml",
                                    step["run"],
                                )
                            elif (
                                "go-junit-report" in step["run"]
                                and "-out" in step["run"]
                            ):
                                step["run"] = re.sub(
                                    r"-out [^\s]+",
                                    "-out report.xml",
                                    step["run"],
                                )
                            else:
                                step["run"] = (
                                    step["run"]
                                    + " 2>&1 | ~/go/bin/go-junit-report > report.xml"
                                )

                            step["run"] = new_step_run + step["run"]

    def get_test_results(self, repo_path) -> List[TestCase]:
        parser = JUnitXMLParser()
        return parser.get_test_results(str(Path(repo_path, "report.xml")))

    def get_build_tool(self) -> str:
        return "go"

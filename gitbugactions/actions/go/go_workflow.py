from typing import List, Tuple
from junitparser import TestCase
from pathlib import Path
import re

from gitbugactions.actions.workflow import GitHubWorkflow
from gitbugactions.actions.multi.junitxmlparser import JUnitXMLParser


class GoWorkflow(GitHubWorkflow):
    BUILD_TOOL_KEYWORDS = ["go"]
    # Regex patterns to match go test commands
    __COMMAND_PATTERNS = [
        r"go\s+(([^\s]+\s+)*)?",
    ]
    GITBUG_CACHE = "~/gitbug-cache"

    def _is_test_command(self, command) -> bool:
        return self.__is_command(command, ["test"])[0]

    def __is_command(self, command: str, keywords: list[str]) -> Tuple[bool, str]:
        # Checks if the given command matches any of the command patterns
        for keyword in keywords:
            for pattern in GoWorkflow.__COMMAND_PATTERNS:
                if re.search(pattern + keyword, command):
                    return True, keyword
        return False, ""

    def instrument_online_execution(self):
        if self.has_tests():
            for _, job in self.doc["jobs"].items():
                if "steps" in job:
                    for step in job["steps"]:
                        if "run" in step and self._is_test_command(step["run"]):
                            break
                    else:
                        continue

                    # Job with tests
                    # We need to install the go-test-report package to generate the reports
                    job["steps"].insert(
                        0,
                        {
                            "name": "gitbug-actions install go-junit-report",
                            "run": "go install github.com/jstemmer/go-junit-report/v2@v2.0.0",
                        },
                    )
                    # We need to generate the vendor to keep dependencies
                    job["steps"].append(
                        {
                            "name": "gitbug-actions generate vendor",
                            "run": f"mkdir -p {GoWorkflow.GITBUG_CACHE} && "
                            + "go mod vendor && "
                            + f"cp -r vendor {GoWorkflow.GITBUG_CACHE} || : && "
                            + f"cp go.mod {GoWorkflow.GITBUG_CACHE} || : && "
                            + f"cp go.sum {GoWorkflow.GITBUG_CACHE} || :",
                        }
                    )
                    return

    def instrument_offline_execution(self):
        if self.has_tests():
            for _, job in self.doc["jobs"].items():
                has_tests = False
                if "steps" in job:
                    for step in job["steps"]:
                        # Removes the actions added in the online execution
                        if "name" in step and step["name"] in [
                            "gitbug-actions install go-junit-report",
                            "gitbug-actions generate vendor",
                        ]:
                            job["steps"].remove(step)

                        if "run" not in step:
                            continue

                        is_mod_command, keyword = self.__is_command(
                            step["run"], ["build", "fmt", "run", "install", "test"]
                        )
                        if is_mod_command:
                            if "-mod" not in step["run"]:
                                step["run"] = re.sub(
                                    keyword,
                                    keyword + " -mod=vendor",
                                    step["run"],
                                )
                            else:
                                step["run"] = re.sub(
                                    r"-mod=[^\s]+|-mod [^\s]+",
                                    "-mod=vendor",
                                    step["run"],
                                )
                            has_tests = True

                    if has_tests:
                        job["steps"].insert(
                            0,
                            {
                                "name": "restore vendor",
                                "run": f"cp -r {GoWorkflow.GITBUG_CACHE}/vendor . || : && "
                                + f"cp {GoWorkflow.GITBUG_CACHE}/go.mod . || : && "
                                + f"cp {GoWorkflow.GITBUG_CACHE}/go.sum . || :",
                            },
                        )

    def instrument_test_steps(self):
        if "jobs" in self.doc:
            for _, job in self.doc["jobs"].items():
                if "steps" in job:
                    for step in job["steps"]:
                        if "run" in step and self._is_test_command(step["run"]):
                            step["run"] = step["run"].strip()

                            if "-v" not in step["run"]:
                                step["run"] = re.sub(
                                    r"test",
                                    "test -v",
                                    step["run"],
                                )
                            if "go-junit-report" in step["run"] and ">" in step["run"]:
                                step["run"] = re.sub(
                                    r"> [^\s]+$",
                                    "> report.xml",
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

    def get_test_results(self, repo_path) -> List[TestCase]:
        parser = JUnitXMLParser()
        return parser.get_test_results(str(Path(repo_path, "report.xml")))

    def get_build_tool(self) -> str:
        return "go"

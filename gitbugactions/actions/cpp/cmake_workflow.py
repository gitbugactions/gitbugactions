import re, os, glob
from typing import List

from junitparser import TestCase, Error

from gitbugactions.actions.multi.junitxmlparser import JUnitXMLParser
from gitbugactions.actions.workflow import GitHubWorkflow


class CMakeWorkflow(GitHubWorkflow):
    BUILD_TOOL_KEYWORDS = {"cmake"}

    def __init__(self, path: str, workflow: str = ""):
        super().__init__(path, workflow)
        self.prune_unsupported_workflow()
        self.result_file = "report.xml"

    def _is_test_command(self, command) -> bool:
        return "ctest" in command

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

                # CMake doesn't support 'ctest --output-junit' before 3.21.4
                if "env" not in job:
                    job["env"] = {"CMAKE_VERSION": "3.31.5"}
                else:
                    job["env"]["CMAKE_VERSION"] = "3.31.5"

    def get_test_results(self, repo_path) -> List[TestCase]:
        search_path = os.path.join(repo_path, "**", self.result_file)
        files = glob.glob(search_path, recursive=True)
        if files:
            parser = JUnitXMLParser()
            return parser.get_test_results(files[0])
        return []

    def get_build_tool(self) -> str:
        return "cmake"

    def prune_unsupported_workflow(self):
        if "name" in self.doc and "jobs" in self.doc:
            if self.doc["name"] in [
                "CIFuzz",
                "Build cxxopts",
                "Feature CI",
                "Alpine Linux",
            ]:
                del self.doc["jobs"]

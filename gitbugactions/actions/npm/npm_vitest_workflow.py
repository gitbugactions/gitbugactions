from pathlib import Path
from typing import List

from junitparser import TestCase

from gitbugactions.actions.multi.junitxmlparser import JUnitXMLParser
from gitbugactions.actions.npm.npm_workflow import NpmWorkflow


class NpmVitestWorkflow(NpmWorkflow):

    @classmethod
    def is_npm_test_command(cls, command: str) -> bool:
        return "vitest" in command.lower()

    def instrument_test_steps(self, **kwargs):
        if "jobs" in self.doc:
            for _, job in self.doc["jobs"].items():
                if "steps" in job:
                    for step in job["steps"]:
                        if "run" in step and self._is_test_command(step["run"]):
                            step["run"] = (
                                f"{step['run']} -- --reporter=junit --outputFile=junit.xml"
                            )

    def get_test_results(self, repo_path) -> List[TestCase]:
        parser = JUnitXMLParser()
        return parser.get_test_results(str(Path(repo_path, "junit.xml")))

    def get_build_tool(self) -> str:
        return "npm-vitest"

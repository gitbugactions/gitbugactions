from pathlib import Path
from typing import List

from junitparser import TestCase

from gitbugactions.actions.multi.junitxmlparser import JUnitXMLParser
from gitbugactions.actions.npm.npm_workflow import NpmWorkflow


class NpmMochaWorkflow(NpmWorkflow):

    @classmethod
    def is_npm_test_command(cls, command: str) -> bool:
        return "mocha" in command.lower()

    def instrument_test_steps(self):
        if "jobs" in self.doc:
            for _, job in self.doc["jobs"].items():
                if "steps" in job:
                    for step in job["steps"]:
                        if "run" in step and self._is_test_command(step["run"]):
                            step[
                                "run"
                            ] = f"""npm install --save-dev mocha-junit-reporter
{step['run']} -- --reporter mocha-junit-reporter --reporter-options mochaFile=./test-results.xml"""

    def get_test_results(self, repo_path) -> List[TestCase]:
        parser = JUnitXMLParser()
        return parser.get_test_results(str(Path(repo_path, "test-results.xml")))

    def get_build_tool(self) -> str:
        return "npm-mocha"

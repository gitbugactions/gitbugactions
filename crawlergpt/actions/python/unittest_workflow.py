from typing import List
from junitparser import TestCase
from pathlib import Path
import re

from crawlergpt.actions.workflow import GitHubWorkflow
from crawlergpt.actions.multi.junitxmlparser import JUnitXMLParser

class UnittestWorkflow(GitHubWorkflow):
    __TESTS_KEYWORDS = ["unittest", "xmlrunner"]

    def _is_test_keyword(self, name):
        return any(map(lambda word: word.lower() in UnittestWorkflow.__TESTS_KEYWORDS, name.split(' ')))

    def instrument_test_steps(self):
        for job_name, job in self.doc['jobs'].items():
            if 'steps' in job:
                for step in job['steps']:
                    if 'run' in step and self._is_test_keyword(step['run']):
                        # We need to install the xmlrunner package to generate the reports
                        new_step_run = "pip install unittest-xml-reporting && "
                        if "-m unittest" in step['run']:
                            # Replace the unittest command with the xmlrunner command
                            new_step_run += step['run'].replace("-m unittest", "-m xmlrunner -o ./test_reports")
                        elif "-m xmlrunner" in step['run'] and "-o" not in step['run']:
                            # Add the output folder to the xmlrunner command
                            new_step_run += step['run'].replace("-m xmlrunner", "-m xmlrunner -o ./test_reports")
                        elif "-m xmlrunner" in step['run'] and "-o" in step['run']:
                            # Replace the output folder with the test_reports folder
                            new_step_run += re.sub(r"-o [^\s]+", "-o ./test_reports", step['run'])
                        else:
                            # We don't know how to instrument this command
                            new_step_run += step['run']
                        step['run'] = new_step_run

    def get_test_results(self, repo_path) -> List[TestCase]:
        parser = JUnitXMLParser()
        return parser.get_test_results(str(Path(repo_path, "test_reports")))

    def get_build_tool(self) -> str:
        return "unittest" 
from typing import List
from junitparser import TestCase
from pathlib import Path

from crawlergpt.actions.workflow import GitHubWorkflow
from crawlergpt.actions.multi.junitxmlparser import JUnitXMLParser

class PytestWorkflow(GitHubWorkflow): 
    __TESTS_KEYWORDS = ["pytest"]
    
    def _is_test_keyword(self, name):
        return any(map(lambda word: word.lower() in PytestWorkflow.__TESTS_KEYWORDS, name.split(' ')))
    
    def instrument_test_steps(self):
        for job_name, job in self.doc['jobs'].items():
            if 'steps' in job:
                for step in job['steps']:
                    if 'run' in step and self._is_test_keyword(step['run']):
                        if "pytest" in step['run']:
                            step['run'] = step['run'].replace("pytest", "pytest --junitxml=report.xml")
                            
    def get_failed_tests(self, repo_path) -> List[TestCase]:
        parser = JUnitXMLParser()
        return parser.get_failed_tests(str(Path(repo_path, "report.xml")))
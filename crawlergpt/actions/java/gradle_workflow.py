from typing import List
from junitparser import TestCase
from pathlib import Path

from crawlergpt.actions.workflow import GitHubWorkflow
from crawlergpt.actions.multi.junitxmlparser import JUnitXMLParser

class GradleWorkflow(GitHubWorkflow):
    # Correspond to the gradle lifecycle phases that run tests
    __TESTS_KEYWORDS = ["test", "check", "build", "buildDependents", "buildNeeded", ]
    
    def _is_test_keyword(self, name):
        return any(map(lambda word: word.lower() in GradleWorkflow.__TESTS_KEYWORDS, name.split(' ')))
    
    def instrument_test_steps(self):
        pass
    
    def get_test_results(self, repo_path) -> List[TestCase]:
        parser = JUnitXMLParser()
        return parser.get_test_results(str(Path(repo_path, "build", "test-results", "test")))
    
    def get_build_tool(self) -> str:
        return "gradle"
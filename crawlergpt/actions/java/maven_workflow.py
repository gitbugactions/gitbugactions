from typing import List
from junitparser import TestCase
from pathlib import Path

from crawlergpt.actions.workflow import GitHubWorkflow
from crawlergpt.actions.multi.junitxmlparser import JUnitXMLParser

class MavenWorkflow(GitHubWorkflow):
    # Correspond to the maven lifecycle phases that run tests
    # https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html#Lifecycle_Reference
    __TESTS_KEYWORDS = ["test", "package", "integration-test", "verify", "install"]
    
    def _is_test_keyword(self, name):
        return any(map(lambda word: word.lower() in MavenWorkflow.__TESTS_KEYWORDS, name.split(' ')))
    
    def instrument_test_steps(self):
        pass
    
    def get_test_results(self, repo_path) -> List[TestCase]:
        parser = JUnitXMLParser()
        return parser.get_test_results(str(Path(repo_path, "target", "surefire-reports")))
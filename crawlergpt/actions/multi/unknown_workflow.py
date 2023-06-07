from typing import List
from junitparser import TestCase

from crawlergpt.actions.workflow import GitHubWorkflow

class UnknownWorkflow(GitHubWorkflow):
    # Represnts a workflow whose build tool is either:
    # 1. not supported by CrawlerGPT, or
    # 2. not identified by CrawlerGPT
    
    def _is_test_keyword(self, name):
        return False
    
    def instrument_test_steps(self):
        pass
    
    def get_failed_tests(self, repo_path) -> List[TestCase]:
        return []
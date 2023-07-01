from typing import List
from junitparser import TestCase

from crawlergpt.actions.workflow import GitHubWorkflow


class UnknownWorkflow(GitHubWorkflow):
    # Represents a workflow whose build tool is either:
    # 1. not supported by CrawlerGPT, or
    # 2. not identified by CrawlerGPT

    def _is_test_command(self, command) -> bool:
        return False

    def instrument_test_steps(self):
        pass

    def get_test_results(self, repo_path) -> List[TestCase]:
        return []

    def get_build_tool(self) -> str:
        return "unknown"

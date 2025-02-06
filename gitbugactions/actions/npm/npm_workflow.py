from abc import abstractmethod
from typing import Tuple

import re

from gitbugactions.actions.workflow import GitHubWorkflow


class NpmWorkflow(GitHubWorkflow):
    BUILD_TOOL_KEYWORDS = {"npm"}
    # Regex patterns to match npm test commands
    NPM_COMMANDS_PATTERNS = r"npm"
    TEST_COMMANDS_PATTERNS = [
        r"(test(?::\S*)*)",
        r"(run\s+test(?::\S*)*)",
        r"(run\s+coverage(?::\S*)*)",
    ]

    @classmethod
    def _get_test_script(self, command: str) -> Tuple[bool, str]:
        for test_pattern in NpmWorkflow.TEST_COMMANDS_PATTERNS:
            pattern = NpmWorkflow.NPM_COMMANDS_PATTERNS + r"\s+" + test_pattern
            if re.search(pattern, command):
                match = re.search(pattern, command)
                return True, match.group(1)
        return False, ""

    # FIXME: name is confusing, "command" here means "script" in the context of npm
    # but the name is "command" because of the abstract interface
    def _is_test_command(self, command):
        return self._get_test_script(command)[0]

    @classmethod
    @abstractmethod
    def is_npm_test_command(cls, command: str) -> bool:
        pass

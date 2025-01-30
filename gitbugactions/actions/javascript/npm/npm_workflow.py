from typing import Tuple
from abc import abstractmethod
import re
import json
import os
import inspect

from gitbugactions.actions.workflow import GitHubWorkflow
from gitbugactions.actions.multi.unknown_workflow import UnknownWorkflow
from gitbugactions.utils.file_reader import FileReader


class NpmWorkflow(GitHubWorkflow):
    BUILD_TOOL_KEYWORDS = {"npm"}
    # Regex patterns to match npm test commands
    __NPM_COMMANDS_PATTERNS = r"npm"
    __TEST_COMMANDS_PATTERNS = [r"(test(?::\S*)*)", r"(run\s+test(?::\S*)*)"]

    @classmethod
    def create_specific_workflow(
        cls, path: str, content: str, file_reader: FileReader
    ) -> "NpmWorkflow":
        """Factory method to create specific npm workflow based on package.json"""
        # Remove explicit imports as they're no longer needed

        # Get package.json content
        workflow_dir = os.path.join(os.path.dirname(path), "..", "..")
        package_json_path = os.path.join(workflow_dir, "package.json")
        package_content = file_reader.read_file(package_json_path)

        if package_content:
            try:
                package_data = json.loads(package_content)
                scripts = package_data.get("scripts", {})
                # TODO: The script name should be configurable, and come from the pattern matching done when identifying the build tool
                test_script = scripts.get("test", "")

                # Dynamically get all non-abstract subclasses of NpmWorkflow
                workflows = [
                    subcls
                    for subcls in cls.__subclasses__()
                    if not inspect.isabstract(subcls)
                ]

                # Try each specific workflow
                for workflow_class in workflows:
                    if workflow_class._is_test_script(test_script):
                        return workflow_class(path, content)
            except json.JSONDecodeError:
                pass

        return UnknownWorkflow(path, content)

    def _is_test_command(self, command) -> bool:
        return self._is_test_script(command)[0]

    def _get_test_command(self, command: str) -> Tuple[bool, str]:
        for test_pattern in self.__TEST_COMMANDS_PATTERNS:
            if re.search(self.__NPM_COMMANDS_PATTERNS + r"\s+" + test_pattern, command):
                match = re.search(test_pattern, command)
                return True, match.group(1)
        return False, ""

    @abstractmethod
    def _is_test_script(test_script: str) -> bool:
        """Abstract method to check if this workflow matches the test script"""
        return False

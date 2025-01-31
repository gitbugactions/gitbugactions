from typing import Tuple
from abc import abstractmethod
import re
import json
import os
import inspect
import yaml

from gitbugactions.actions.workflow import GitHubWorkflow
from gitbugactions.actions.multi.unknown_workflow import UnknownWorkflow
from gitbugactions.utils.file_reader import FileReader


class NpmWorkflow(GitHubWorkflow):
    BUILD_TOOL_KEYWORDS = {"npm"}
    # Regex patterns to match npm test commands
    __NPM_COMMANDS_PATTERNS = r"npm"
    __TEST_COMMANDS_PATTERNS = [
        r"(test(?::\S*)*)",
        r"(run\s+test(?::\S*)*)",
        r"(run\s+coverage(?::\S*)*)",
    ]

    @classmethod
    def create_specific_workflow(
        cls, path: str, content: str, file_reader: FileReader
    ) -> "NpmWorkflow":
        """Factory method to create specific npm workflow based on package.json"""
        # Search for npm test commands in the workflow
        # Load document
        doc = yaml.safe_load(content)
        if doc is None:
            return None

        if True in doc:
            doc["on"] = doc[True]
            doc.pop(True)

        # Iterate over the workflow to find npm test commands
        is_test_script, test_script = False, ""
        if "jobs" in doc and isinstance(doc["jobs"], dict):
            for _, job in doc["jobs"].items():
                if "steps" in job:
                    for step in job["steps"]:
                        if "run" in step:
                            is_test_script, test_script = cls.__get_test_script(
                                step["run"]
                            )
                            if is_test_script:
                                break
        if not is_test_script:
            return UnknownWorkflow(path, content)

        # Get package.json content
        workflow_dir = os.path.join(os.path.dirname(path), "..", "..")
        package_json_path = os.path.join(workflow_dir, "package.json")
        package_content = file_reader.read_file(package_json_path)

        # Check if package.json exists
        if package_content:
            try:
                # Process test script
                test_script = test_script.strip()
                # Remove "run " prefix if present
                if test_script.startswith("run "):
                    test_script = test_script[4:].strip()

                package_data = json.loads(package_content)
                scripts = package_data.get("scripts", {})
                test_command = scripts.get(test_script, None)
                if test_command is None:
                    return UnknownWorkflow(path, content)

                # Dynamically get all non-abstract subclasses of NpmWorkflow
                workflow_classes = [
                    subcls
                    for subcls in cls.__subclasses__()
                    if not inspect.isabstract(subcls)
                ]

                # Try each specific workflow
                for workflow_class in workflow_classes:
                    if workflow_class.is_npm_test_command(test_command):
                        return workflow_class(path, content)
            except json.JSONDecodeError:
                pass

        return UnknownWorkflow(path, content)

    @classmethod
    def __get_test_script(self, command: str) -> Tuple[bool, str]:
        for test_pattern in self.__TEST_COMMANDS_PATTERNS:
            pattern = self.__NPM_COMMANDS_PATTERNS + r"\s+" + test_pattern
            if re.search(pattern, command):
                match = re.search(test_pattern, command)
                return True, match.group(1)
        return False, ""

    # FIXME: name is confusing, "command" here means "script" in the context of npm
    # but the name is "command" because of the abstract interface
    def _is_test_command(self, command):
        return self.__get_test_script(command)[0]

    @classmethod
    @abstractmethod
    def is_npm_test_command(cls, command: str) -> bool:
        pass

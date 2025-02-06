from typing import List, Type

import os
import re
import yaml
import json
import inspect

from gitbugactions.actions.multi.unknown_workflow import UnknownWorkflow
from gitbugactions.actions.npm.npm_workflow import NpmWorkflow
from gitbugactions.utils.file_reader import FileReader

# Import all npm workflow subclasses here
from gitbugactions.actions.npm.npm_jest_workflow import NpmJestWorkflow
from gitbugactions.actions.npm.npm_mocha_workflow import NpmMochaWorkflow
from gitbugactions.actions.npm.npm_vitest_workflow import NpmVitestWorkflow

# Add other npm workflow imports as needed


class NpmWorkflowFactory:
    """
    Factory class for creating NpmWorkflow workflow objects.
    """

    @classmethod
    def __get_workflow_subclasses(cls) -> List[Type["NpmWorkflow"]]:
        """Get all concrete (non-abstract) subclasses of NpmWorkflow."""

        def get_all_subclasses(c):
            subclasses = set(c.__subclasses__())
            return subclasses.union(
                s for c in subclasses for s in get_all_subclasses(c)
            )

        return [
            subcls
            for subcls in get_all_subclasses(NpmWorkflow)
            if not inspect.isabstract(subcls)
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
        def find_npm_test_commands(doc):
            is_test_script, test_script = False, ""
            if "jobs" in doc and isinstance(doc["jobs"], dict):
                for _, job in doc["jobs"].items():
                    if "steps" in job:
                        for step in job["steps"]:
                            if "run" in step:
                                is_test_script, test_script = (
                                    NpmWorkflow._get_test_script(step["run"])
                                )
                                if is_test_script:
                                    return is_test_script, test_script
            return is_test_script, test_script

        is_test_script, test_script = find_npm_test_commands(doc)
        if not is_test_script:
            return UnknownWorkflow(path, content)

        # Get package.json content
        repo_dir = os.path.join(os.path.dirname(path), "..", "..")
        package_json_path = os.path.join(repo_dir, "package.json")
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

                # Get all concrete workflow subclasses
                workflow_classes = cls.__get_workflow_subclasses()

                # Try each specific workflow
                for workflow_class in workflow_classes:
                    if workflow_class.is_npm_test_command(test_command):
                        return workflow_class(path, content)
            except json.JSONDecodeError:
                pass

        return UnknownWorkflow(path, content)

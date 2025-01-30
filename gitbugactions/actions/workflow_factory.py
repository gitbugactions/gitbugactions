from gitbugactions.actions.go.go_workflow import GoWorkflow
from gitbugactions.actions.java.gradle_workflow import GradleWorkflow
from gitbugactions.actions.java.maven_workflow import MavenWorkflow
from gitbugactions.actions.javascript.npm_jest_workflow import NpmJestWorkflow
from gitbugactions.actions.javascript.npm_mocha_workflow import NpmMochaWorkflow
from gitbugactions.actions.multi.unknown_workflow import UnknownWorkflow
from gitbugactions.actions.python.pytest_workflow import PytestWorkflow
from gitbugactions.actions.python.unittest_workflow import UnittestWorkflow
from gitbugactions.actions.workflow import GitHubWorkflow
from gitbugactions.utils.file_reader import FileReader, RegularFileReader


from typing import Optional

import yaml
import json
import logging
import os


class GitHubWorkflowFactory:
    """
    Factory class for creating workflow objects.
    """

    @staticmethod
    def _identify_build_tool(path: str, file_reader: FileReader) -> Optional[str]:
        """
        Identifies the build tool used by the workflow.
        """
        # Build tool keywords
        try:
            build_tool_keywords = {
                "maven": MavenWorkflow.BUILD_TOOL_KEYWORDS,
                "gradle": GradleWorkflow.BUILD_TOOL_KEYWORDS,
                "pytest": PytestWorkflow.BUILD_TOOL_KEYWORDS,
                "unittest": UnittestWorkflow.BUILD_TOOL_KEYWORDS,
                "go": GoWorkflow.BUILD_TOOL_KEYWORDS,
                "npm": NpmJestWorkflow.BUILD_TOOL_KEYWORDS
                | NpmMochaWorkflow.BUILD_TOOL_KEYWORDS,
            }
            aggregate_keywords = {kw for _ in build_tool_keywords.values() for kw in _}
            keyword_counts = {keyword: 0 for keyword in aggregate_keywords}
            aggregate_keyword_counts = {
                build_tool: 0 for build_tool in build_tool_keywords
            }

            def _update_keyword_counts(keyword_counts, phrase):
                if isinstance(phrase, str):
                    for name in phrase.strip().lower().split(" "):
                        for keyword in aggregate_keywords:
                            if keyword in name:
                                keyword_counts[keyword] += 1

            # Load the workflow
            content = file_reader.read_file(path)
            if content is None:
                return None

            doc = yaml.safe_load(content)
            if doc is None:
                return None

            if True in doc:
                doc["on"] = doc[True]
                doc.pop(True)

            # Iterate over the workflow to find build tool names in the run commands
            if "jobs" in doc and isinstance(doc["jobs"], dict):
                for _, job in doc["jobs"].items():
                    if "steps" in job:
                        for step in job["steps"]:
                            if "run" in step:
                                _update_keyword_counts(keyword_counts, step["run"])

            # Aggregate keyword counts per build tool
            for build_tool in build_tool_keywords:
                for keyword in build_tool_keywords[build_tool]:
                    aggregate_keyword_counts[build_tool] += keyword_counts[keyword]

            # Return the build tool with the highest count
            max_build_tool = max(
                aggregate_keyword_counts, key=aggregate_keyword_counts.get
            )
            return (
                max_build_tool if aggregate_keyword_counts[max_build_tool] > 0 else None
            )
        except yaml.YAMLError:
            return None

    @staticmethod
    def _identify_test_framework(
        path: str, build_tool: Optional[str], file_reader: FileReader
    ) -> Optional[str]:
        """
        Identifies the test framework used by the workflow.
        Currently only used for npm projects, checks package.json for testing framework.
        For other build tools, returns the build tool name.
        """
        # TODO: move this function inside build tool classes, to separate logic and make it more modular
        if build_tool != "npm":
            return build_tool

        try:
            # path is the workflow file path, so we need to go up two directories to find the root of the project
            workflow_dir = os.path.join(os.path.dirname(path), "..", "..")
            package_json_path = os.path.join(workflow_dir, "package.json")

            content = file_reader.read_file(package_json_path)
            if content is None:
                return build_tool

            package_data = json.loads(content)

            # Check both dependencies and devDependencies for Jest
            dependencies = package_data.get("dependencies", {})
            dev_dependencies = package_data.get("devDependencies", {})

            if "jest" in dependencies or "jest" in dev_dependencies:
                return "jest"

            # Check if test script contains jest command
            scripts = package_data.get("scripts", {})
            test_script = scripts.get("test", "")
            if "jest" in test_script.lower():
                return "jest"

            # Check for Mocha
            if (
                "mocha" in dependencies
                or "mocha" in dev_dependencies
                or "mocha" in test_script
            ):
                return "mocha"

            return build_tool

        except (json.JSONDecodeError, Exception):
            logging.warning(f"Failed to parse package.json for {path}")
            return build_tool

    @staticmethod
    def create_workflow(
        path: str,
        language: str,
        file_reader: FileReader = RegularFileReader(),
    ) -> GitHubWorkflow:
        """
        Creates a workflow object according to the language and build system.
        """
        content = file_reader.read_file(path)
        if content is None:
            return UnknownWorkflow(path, "")

        build_tool = GitHubWorkflowFactory._identify_build_tool(path, file_reader)
        test_framework = GitHubWorkflowFactory._identify_test_framework(
            path, build_tool, file_reader
        )

        match (language, build_tool, test_framework):
            case ("java", "maven", "maven"):
                return MavenWorkflow(path, content)
            case ("java", "gradle", "gradle"):
                return GradleWorkflow(path, content)
            case ("python", "pytest", "pytest"):
                return PytestWorkflow(path, content)
            case ("python", "unittest", "unittest"):
                return UnittestWorkflow(path, content)
            case ("go", "go", "go"):
                return GoWorkflow(path, content)
            case ("javascript", "npm", "jest"):
                return NpmJestWorkflow(path, content)
            case ("javascript", "npm", "mocha"):
                return NpmMochaWorkflow(path, content)
            case (_, _, _):
                return UnknownWorkflow(path, content)

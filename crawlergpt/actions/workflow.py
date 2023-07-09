import yaml
import logging
import traceback
from abc import ABC, abstractmethod
from junitparser import TestCase
from typing import List, Set
from crawlergpt.github_token import GithubToken
from crawlergpt.actions.action import Action


class GitHubWorkflow(ABC):
    __UNSUPPORTED_OS = [
        "windows-latest",
        "windows-2022",
        "windows-2019",
        "windows-2016",
        "macos-13",
        "macos-13-xl",
        "macos-latest",
        "macos-12",
        "macos-latest-xl",
        "macos-12-xl",
        "macos-11",
        "ubuntu-22.04",
        "ubuntu-20.04",
        "ubuntu-18.04",
    ]

    def __init__(self, path: str, workflow: str = ""):
        try:
            if workflow == "":
                with open(path, "r") as stream:
                    self.doc = yaml.safe_load(stream)
            else:
                self.doc = yaml.safe_load(workflow)
            # Solves problem where pyyaml parses 'on' (used in Github actions) as True
            if True in self.doc:
                self.doc["on"] = self.doc[True]
                self.doc.pop(True)
        except Exception:
            self.doc = []
        self.path = path
        self.tokens: List[GithubToken] = []

    @abstractmethod
    def _is_test_command(self, command) -> bool:
        """
        Checks if a given command is a test command

        Returns:
            bool: True if the command is a test command
        """
        pass

    def has_tests(self) -> bool:
        """
        Check if the workflow has any tests.

        Returns:
            bool: True if the workflow has tests, False otherwise.
        """
        try:
            # Check if any run command is a test running command
            if "jobs" in self.doc:
                for _, job in self.doc["jobs"].items():
                    if "steps" in job:
                        for step in job["steps"]:
                            if "run" in step and self._is_test_command(step["run"]):
                                return True
            return False
        except yaml.YAMLError:
            return False

    def get_actions(self) -> Set[Action]:
        actions: Set[Action] = set()
        if "jobs" in self.doc:
            for _, job in self.doc["jobs"].items():
                if "steps" in job:
                    for step in job["steps"]:
                        if "uses" in step:
                            try:
                                action = Action(step["uses"])
                            except Exception:
                                logging.warning(
                                    f"Failed to parse action {step['uses']}"
                                )
                                continue
                            actions.add(action)

        return actions

    def instrument_os(self):
        """
        Instruments the workflow to run only on ubuntu-latest (due to act compatibility).
        """

        def walk_doc(doc):
            """
            Walks the document recursively and replaces any unsupported OS with Ubuntu.
            """
            if isinstance(doc, dict):
                for key, value in doc.items():
                    if str(value).lower() in GitHubWorkflow.__UNSUPPORTED_OS:
                        doc[key] = "ubuntu-latest"
                    else:
                        walk_doc(value)
            elif isinstance(doc, list):
                doc[:] = filter(
                    lambda x: str(x).lower() not in GitHubWorkflow.__UNSUPPORTED_OS, doc
                )
                for value in doc:
                    walk_doc(value)
                if len(doc) == 0:
                    doc.append("ubuntu-latest")

        # Replace any unsupported OS with Ubuntu
        if "jobs" in self.doc:
            for _, job in self.doc["jobs"].items():
                if (
                    "runs-on" in job
                    and str(job["runs-on"]).lower() in GitHubWorkflow.__UNSUPPORTED_OS
                ):
                    job["runs-on"] = "ubuntu-latest"
                if (
                    "strategy" in job
                    and "os" in job["strategy"]
                    and isinstance(job["strategy"]["os"], list)
                ):
                    job["strategy"]["os"] = ["ubuntu-latest"]
                if "strategy" in job:
                    walk_doc(job["strategy"])

    def instrument_strategy(self):
        """
        Instruments the workflow to run only one configuration (the fisrt one) per job.
        """
        if "jobs" in self.doc:
            for _, job in self.doc["jobs"].items():
                if "strategy" in job and "matrix" in job["strategy"]:
                    for key, value in job["strategy"]["matrix"].items():
                        if isinstance(value, list):
                            job["strategy"]["matrix"][key] = [value[0]]

    def instrument_setup_steps(self):
        if not GithubToken.has_tokens():
            return
        self.tokens = []

        if "jobs" in self.doc:
            for _, job in self.doc["jobs"].items():
                if "steps" not in job:
                    continue

                for step in job["steps"]:
                    if "uses" not in step or "setup" not in step["uses"]:
                        continue

                    if "with" in step and "token" not in step["with"]:
                        token = GithubToken.get_token()
                        step["with"]["token"] = token.token
                        self.tokens.append(token)
                    elif "with" not in step:
                        token = GithubToken.get_token()
                        step["with"] = {"token": token.token}
                        self.tokens.append(token)

    def instrument_offline_execution(self):
        """
        Instruments the workflow for an offline execution. Only keeps steps
        related to the execution of tests.
        """
        if "jobs" in self.doc:
            for _, job in self.doc["jobs"].items():
                test_steps = []

                if "steps" in job:
                    for step in job["steps"]:
                        if "run" in step and self._is_test_command(step["run"]):
                            test_steps.append(step)
                    job["steps"] = test_steps

    def instrument_jobs(self):
        """
        Instruments the workflow to keep only the jobs containing test commands.
        If the job has dependencies (needs), then keep those jobs too.
        """

        def get_needs(job_name: str) -> List[str]:
            if (
                job_name not in self.doc["jobs"]
                or "needs" not in self.doc["jobs"][job_name]
            ):
                return []

            needed_jobs = self.doc["jobs"][job_name]["needs"]
            if isinstance(needed_jobs, list):
                for needed_job in needed_jobs:
                    needed_jobs += get_needs(needed_job)
            else:
                needed_jobs = [needed_jobs] + get_needs(needed_jobs)

            return needed_jobs

        if "jobs" in self.doc:
            required_jobs = set()
            for job_name, job in self.doc["jobs"].items():
                has_test = False
                if "steps" in job:
                    for step in job["steps"]:
                        if "run" in step and self._is_test_command(step["run"]):
                            has_test = True

                if has_test:
                    required_jobs.add(job_name)
                    required_jobs.update(get_needs(job_name))

            self.doc["jobs"] = {
                job_name: job
                for job_name, job in self.doc["jobs"].items()
                if job_name in required_jobs
            }

    @abstractmethod
    def instrument_test_steps(self):
        """
        Instruments the test steps to generate reports.
        """
        pass

    @abstractmethod
    def get_test_results(self, repo_path) -> List[TestCase]:
        """
        Gets the test results from the workflow.
        """
        pass

    @abstractmethod
    def get_build_tool(self) -> str:
        """
        Gets the name of the build tool used by the workflow.
        """
        pass

    def save_yaml(self, new_path):
        with open(new_path, "w") as file:
            yaml.dump(self.doc, file)


from crawlergpt.actions.multi.unknown_workflow import UnknownWorkflow
from crawlergpt.actions.java.maven_workflow import MavenWorkflow
from crawlergpt.actions.java.gradle_workflow import GradleWorkflow
from crawlergpt.actions.python.pytest_workflow import PytestWorkflow
from crawlergpt.actions.python.unittest_workflow import UnittestWorkflow


class GitHubWorkflowFactory:
    """
    Factory class for creating workflow objects.
    """

    @staticmethod
    def _identify_build_tool(path: str, content: str = ""):
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
            }
            aggregate_keywords = {kw for _ in build_tool_keywords.values() for kw in _}
            keyword_counts = {keyword: 0 for keyword in aggregate_keywords}
            aggregate_keyword_counts = {
                build_tool: 0 for build_tool in build_tool_keywords
            }

            def _update_keyword_counts(keyword_counts, phrase):
                for name in phrase.strip().lower().split(" "):
                    for keyword in aggregate_keywords:
                        if keyword in name:
                            keyword_counts[keyword] += 1

            # Load the workflow
            doc = None
            if content == "":
                with open(path, "r") as stream:
                    doc = yaml.safe_load(stream)
            else:
                doc = yaml.safe_load(content)

            if True in doc:
                doc["on"] = doc[True]
                doc.pop(True)

            # Iterate over the workflow to find build tool names in the run commands
            if "jobs" in doc:
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
    def create_workflow(path: str, language: str, content: str = "") -> GitHubWorkflow:
        """
        Creates a workflow object according to the language and build system.
        """
        build_tool = GitHubWorkflowFactory._identify_build_tool(path, content=content)

        match (language, build_tool):
            case ("java", "maven"):
                return MavenWorkflow(path, content)
            case ("java", "gradle"):
                return GradleWorkflow(path, content)
            case ("python", "pytest"):
                return PytestWorkflow(path, content)
            case ("python", "unittest"):
                return UnittestWorkflow(path, content)
            case (_, _):
                return UnknownWorkflow(path, content)

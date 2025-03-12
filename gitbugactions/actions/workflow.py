import logging
from abc import ABC, abstractmethod
from typing import List, Set

import yaml
from junitparser import TestCase

from gitbugactions.actions.action import Action
from gitbugactions.github_api import GithubToken


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
            if "jobs" in self.doc and isinstance(self.doc["jobs"], dict):
                for _, job in self.doc["jobs"].items():
                    if "steps" in job and isinstance(job["steps"], list):
                        for step in job["steps"]:
                            if "run" in step and self._is_test_command(step["run"]):
                                return True
            return False
        except yaml.YAMLError:
            return False

    def get_actions(self) -> Set[Action]:
        actions: Set[Action] = set()
        if "jobs" in self.doc and isinstance(self.doc["jobs"], dict):
            for _, job in self.doc["jobs"].items():
                if "steps" in job and isinstance(job["steps"], list):
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

    def has_matrix_include_exclude(self) -> bool:
        """
        Check if the workflow has a job with a matrix with include/exclude options
        """
        if "jobs" in self.doc and isinstance(self.doc["jobs"], dict):
            for _, job in self.doc["jobs"].items():
                if (
                    "strategy" in job
                    and isinstance(job["strategy"], dict)
                    and "matrix" in job["strategy"]
                ):
                    if (
                        "include" in job["strategy"]["matrix"]
                        or "exclude" in job["strategy"]["matrix"]
                    ):
                        return True

        return False

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
        if "jobs" in self.doc and isinstance(self.doc["jobs"], dict):
            for _, job in self.doc["jobs"].items():
                if "runs-on" in job:
                    job["runs-on"] = "ubuntu-latest"
                if (
                    "strategy" in job
                    and isinstance(job["strategy"], dict)
                    and "os" in job["strategy"]
                    and isinstance(job["strategy"]["os"], list)
                ):
                    job["strategy"]["os"] = ["ubuntu-latest"]
                if (
                    "strategy" in job
                    and isinstance(job["strategy"], dict)
                    and "matrix" in job["strategy"]
                    and isinstance(job["strategy"]["matrix"], dict)
                    and "os" in job["strategy"]["matrix"]
                ):
                    job["strategy"]["matrix"]["os"] = ["ubuntu-latest"]
                if "strategy" in job:
                    walk_doc(job["strategy"])

    def instrument_strategy(self):
        """
        Instruments the workflow to run only one configuration (the fisrt one) per job.
        """
        if "jobs" in self.doc and isinstance(self.doc["jobs"], dict):
            for _, job in self.doc["jobs"].items():
                if (
                    "strategy" in job
                    and isinstance(job["strategy"], dict)
                    and "matrix" in job["strategy"]
                ):
                    for key, value in job["strategy"]["matrix"].items():
                        if isinstance(value, list):
                            job["strategy"]["matrix"][key] = [value[0]]

    def instrument_setup_steps(self):
        if not GithubToken.has_tokens():
            return
        self.tokens = []

        if "jobs" in self.doc and isinstance(self.doc["jobs"], dict):
            for _, job in self.doc["jobs"].items():
                if "steps" not in job or not isinstance(job["steps"], list):
                    continue

                for step in job["steps"]:
                    if (
                        not isinstance(step, dict)
                        or "uses" not in step
                        or "setup" not in step["uses"]
                    ):
                        continue

                    if (
                        "with" in step
                        and isinstance(step["with"], dict)
                        and "token" not in step["with"]
                    ):
                        token = GithubToken.get_token()
                        step["with"]["token"] = token.token
                        self.tokens.append(token)
                    elif "with" not in step:
                        token = GithubToken.get_token()
                        step["with"] = {"token": token.token}
                        self.tokens.append(token)

    def instrument_offline_execution(self):
        """
        Instruments the workflow for an offline execution.
        """
        pass

    def instrument_online_execution(self):
        """
        Instruments the workflow for an online execution.
        """
        pass

    def instrument_cache_steps(self):
        """
        Act has a problem with the actions/cache and so we must disable the
        usage of this action.
        https://github.com/nektos/act/issues/285
        """
        if "jobs" in self.doc and isinstance(self.doc["jobs"], dict):
            for _, job in self.doc["jobs"].items():
                if "steps" in job and isinstance(job["steps"], list):
                    filtered_steps = []
                    for step in job["steps"]:
                        if not isinstance(step, dict) or (
                            "uses" in step and step["uses"].startswith("actions/cache")
                        ):
                            continue
                        if (
                            "with" in step
                            and isinstance(step["with"], dict)
                            and "cache" in step["with"]
                        ):
                            del step["with"]["cache"]
                        filtered_steps.append(step)
                    job["steps"] = filtered_steps

    def get_jobs(self) -> List[str]:
        """
        Gets the jobs from the workflow.
        """
        jobs = []
        if "jobs" in self.doc and isinstance(self.doc["jobs"], dict):
            for job_name, _ in self.doc["jobs"].items():
                jobs.append(job_name)
        return jobs

    def get_test_jobs(self) -> List[str]:
        """
        Gets the jobs containing test commands.
        """
        test_jobs = []
        if "jobs" in self.doc and isinstance(self.doc["jobs"], dict):
            for job_name, job in self.doc["jobs"].items():
                has_test = False
                if "steps" in job and isinstance(job["steps"], list):
                    for step in job["steps"]:
                        if (
                            isinstance(step, dict)
                            and "run" in step
                            and self._is_test_command(step["run"])
                        ):
                            has_test = True
                if has_test:
                    test_jobs.append(job_name)
        return test_jobs

    def instrument_jobs(self):
        """
        Instruments the workflow to keep only the jobs running on Ubuntu and
        containing test commands. If the job has dependencies (needs), then
        keep those jobs too.
        """

        if "jobs" in self.doc and isinstance(self.doc["jobs"], dict):
            jobs_to_delete = []
            for name, job in self.doc["jobs"].items():
                if "runs-on" in job:
                    if isinstance(job["runs-on"], list):
                        os_to_delete = []
                        for index, runs_on in enumerate(job["runs-on"]):
                            if not runs_on.startswith("ubuntu"):
                                os_to_delete.append(index)

                        job["runs-on"] = [
                            runs_on
                            for index, runs_on in enumerate(job["runs-on"])
                            if index not in os_to_delete
                        ]

                        if len(job["runs-on"]) == 0:
                            jobs_to_delete.append(name)
                        elif len(job["runs-on"]) == 1:
                            job["runs-on"] = job["runs-on"][0]

                    elif not job["runs-on"].startswith("${{"):
                        if not job["runs-on"].startswith("ubuntu"):
                            jobs_to_delete.append(name)

            for job in jobs_to_delete:
                if job in self.doc["jobs"]:
                    del self.doc["jobs"][job]

        def get_needs(job_name: str) -> List[str]:
            if (
                job_name not in self.doc["jobs"]
                or not isinstance(self.doc["jobs"][job_name], dict)
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

        if "jobs" in self.doc and isinstance(self.doc["jobs"], dict):
            required_jobs = set()
            for job_name in self.get_test_jobs():
                required_jobs.add(job_name)
                required_jobs.update(get_needs(job_name))

            self.doc["jobs"] = {
                job_name: job
                for job_name, job in self.doc["jobs"].items()
                if job_name in required_jobs
            }

    def instrument_on_events(self):
        """
        Instruments the workflow to run only on push events.
        """
        if "on" in self.doc:
            self.doc["on"] = "push"

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

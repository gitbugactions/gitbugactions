import yaml
import os
from abc import ABC, abstractmethod
from junitparser import TestCase
from typing import List
from crawlergpt.github_token import GithubToken

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
        "ubuntu-18.04"
    ]


    def __init__(self, path: str):
        with open(path, "r") as stream:
            self.doc = yaml.safe_load(stream)
            self.path = path
            # Solves problem where pyyaml parses 'on' (used in Github actions) as True
            if True in self.doc:
                self.doc['on'] = self.doc[True]
                self.doc.pop(True)
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
            for _, job in self.doc['jobs'].items():
                if 'steps' in job:
                    for step in job['steps']:
                        if 'run' in step and self._is_test_command(step['run']):
                            return True
            return False
        except yaml.YAMLError:
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
                doc[:] = filter(lambda x: str(x).lower() not in GitHubWorkflow.__UNSUPPORTED_OS, doc)
                for value in doc:
                    walk_doc(value)
                if len(doc) == 0:
                    doc.append('ubuntu-latest')

        # Replace any unsupported OS with Ubuntu
        for _, job in self.doc['jobs'].items():
            if 'runs-on' in job and str(job['runs-on']).lower() in GitHubWorkflow.__UNSUPPORTED_OS:
                job['runs-on'] = 'ubuntu-latest'
            if 'strategy' in job and 'os' in job['strategy'] and isinstance(job['strategy']['os'], list):
                job['strategy']['os'] = ['ubuntu-latest']
            if 'strategy' in job:
                walk_doc(job['strategy'])


    def instrument_strategy(self):
        """
        Instruments the workflow to run only one configuration (the fisrt one) per job.
        """
        for _, job in self.doc['jobs'].items():
            if 'strategy' in job and 'matrix' in job['strategy']:
                for key, value in job['strategy']['matrix'].items():
                    if isinstance(value, list):
                        job['strategy']['matrix'][key] = [value[0]]

    
    def instrument_setup_steps(self):
        if not GithubToken.has_tokens():
            return
        self.tokens = []

        for _, job in self.doc['jobs'].items():
            if 'steps' not in job:
                continue

            for step in job['steps']:
                if 'uses' not in step or 'setup' not in step['uses']:
                    continue

                if 'with' in step and 'token' not in step['with']:
                    token = GithubToken.get_token()
                    step['with']['token'] = token.token
                    self.tokens.append(token)
                elif 'with' not in step:
                    token = GithubToken.get_token()
                    step['with'] = {'token': token.token}
                    self.tokens.append(token)


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
        with open(new_path, 'w') as file:
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
    def _identify_build_tool(path: str):
        """
        Identifies the build tool used by the workflow.
        """
        # Build tool keywords
        build_tool_keywords = {
            'maven': MavenWorkflow.BUILD_TOOL_KEYWORDS,
            'gradle': GradleWorkflow.BUILD_TOOL_KEYWORDS,
            'pytest': PytestWorkflow.BUILD_TOOL_KEYWORDS,
            'unittest': UnittestWorkflow.BUILD_TOOL_KEYWORDS,
        }
        aggregate_keywords = {kw for _ in build_tool_keywords.values() for kw in _}
        keyword_counts = {keyword: 0 for keyword in aggregate_keywords}
        
        def _update_keyword_counts(keyword_counts, phrase):
            for name in phrase.strip().lower().split(' '):
                for keyword in aggregate_keywords:
                    if keyword in name:
                        keyword_counts[keyword] += 1
        
        # Load the workflow
        with open(path, "r") as stream:
            doc = yaml.safe_load(stream)
            if True in doc:
                doc['on'] = doc[True]
                doc.pop(True)
                
        # Iterate over the workflow to find build tool names
        for job_name, job in doc['jobs'].items():
            _update_keyword_counts(keyword_counts, job_name)
            if 'steps' in job:
                for step in job['steps']:
                    if 'run' in step:
                        _update_keyword_counts(keyword_counts, step['run'])
                        
        # Return the build tool with the highest count
        max_keyword = max(keyword_counts, key=keyword_counts.get)
        if keyword_counts[max_keyword] > 0:
            for build_tool, keywords in build_tool_keywords.items():
                if max_keyword in keywords:
                    return build_tool
        else:
            return None
        
        
    @staticmethod
    def create_workflow(path: str, language: str):
        """
        Creates a workflow object according to the language and build system.
        """
        build_tool = GitHubWorkflowFactory._identify_build_tool(path)

        match (language, build_tool):
            case ("java", "maven"):
                return MavenWorkflow(path)
            case ("java", "gradle"):
                return GradleWorkflow(path)
            case ("python", "pytest"):
                return PytestWorkflow(path)
            case ("python", "unittest"):
                return UnittestWorkflow(path)
            case (_, _):
                return UnknownWorkflow(path)

import os
import grp
import shutil
import time
import docker
import logging
import subprocess
import threading
import uuid
from typing import List
from junitparser import TestCase, Error
from dataclasses import dataclass
from crawlergpt.actions.workflow import GitHubWorkflow, GitHubWorkflowFactory
from crawlergpt.github_token import GithubToken

@dataclass
class ActTestsRun:
    failed: bool
    tests: List[TestCase]
    stdout: str
    stderr: str
    workflow: str
    build_tool: str
    elapsed_time: int

    @property
    def failed_tests(self):
        failed_tests = []
        for test in self.tests:
            # Check if it is failed (not passed, not skipped and without errors)
            if (not test.is_passed and not test.is_skipped and
                        not any(map(lambda r: isinstance(r, Error), test.result))):
                failed_tests.append(test)
        return failed_tests


class Act:
    __ACT_PATH="act"
    __ACT_SETUP=False
    # The flag -u allows files to be created with the current user
    __FLAGS=f"--bind --pull=false --container-options '-u {os.getuid()}:{os.getgid()}'"
    __DEFAULT_RUNNERS = "-P ubuntu-latest=crawlergpt:latest"
    __SETUP_LOCK = threading.Lock()
    
    
    def __init__(self, reuse, timeout=5):
        '''
        Args:
            timeout (int): Timeout in minutes
        '''
        Act.__setup_act()
        if reuse:
            self.flags = "--reuse"
        else:
            self.flags = "--rm"
        self.timeout = timeout 

    @staticmethod
    def __setup_act():
        Act.__SETUP_LOCK.acquire()
        if Act.__ACT_SETUP:
            Act.__SETUP_LOCK.release()
            return
        # Checks act installation
        run = subprocess.run(f"{Act.__ACT_PATH} --help", shell=True, capture_output=True)
        if run.returncode != 0:
            logging.error("Act is not correctly installed")
            exit(-1)

        # Creates crawler image
        client = docker.from_env()
        if len(client.images.list(name="crawlergpt")) > 0:
            client.images.remove(image="crawlergpt")

        with open("Dockerfile", "w") as f:
            client = docker.from_env()
            dockerfile = "FROM catthehacker/ubuntu:full-latest\n"
            dockerfile += f"RUN usermod -u {os.getuid()} runneradmin\n"
            dockerfile += f"RUN groupadd -o -g {os.getgid()} {grp.getgrgid(os.getgid()).gr_name}\n"
            dockerfile += f"RUN usermod -G {os.getgid()} runneradmin\n"
            f.write(dockerfile)

        client.images.build(path="./", tag="crawlergpt", forcerm=True)
        os.remove("Dockerfile")
        Act.__ACT_SETUP = True
        Act.__SETUP_LOCK.release()


    def run_act(self, repo_path, workflow: GitHubWorkflow) -> ActTestsRun:
        command = f"cd {repo_path}; "
        cache_server_path = f"/tmp/{uuid.uuid4()}"
        command += f"timeout {self.timeout * 60} {Act.__ACT_PATH} {Act.__DEFAULT_RUNNERS} {Act.__FLAGS} {self.flags} --cache-server-path {cache_server_path}"
        if GithubToken.has_tokens():
            token: GithubToken = GithubToken.get_token()
            command += f" -s GITHUB_TOKEN={token.token}"
        command += f" -W {workflow.path}"

        start_time = time.time()
        run = subprocess.run(command, shell=True, capture_output=True)
        end_time = time.time()
        shutil.rmtree(cache_server_path, ignore_errors=True)
        stdout = run.stdout.decode('utf-8')
        stderr = run.stderr.decode('utf-8')
        tests = workflow.get_test_results(repo_path)
        tests_run = ActTestsRun(failed=False, tests=tests, stdout=stdout, 
                stderr=stderr, workflow=workflow.path, build_tool=workflow.get_build_tool(), elapsed_time=end_time - start_time)

        if len(tests_run.failed_tests) == 0 and run.returncode != 0:
            tests_run.failed = True

        if GithubToken.has_tokens():
            token.update_rate_limit()
            for token in workflow.tokens:
                token.update_rate_limit()

        return tests_run


class GitHubActions:
    """
    Class to handle GitHub Actions
    """
    
    def __init__(self, repo_path, language: str):
        self.repo_path = repo_path
        self.language: str = language.strip().lower()
        self.workflows: List[GitHubWorkflow] = []
        self.test_workflows: List[GitHubWorkflow] = []

        workflows_path = os.path.join(repo_path, ".github", "workflows")
        for (dirpath, dirnames, filenames) in os.walk(workflows_path):
            yaml_files = list(filter(lambda file: file.endswith('.yml') or file.endswith('.yaml'), filenames))
            for file in yaml_files:
                # Create workflow object according to the language and build system
                workflow = GitHubWorkflowFactory.create_workflow(os.path.join(dirpath, file), self.language)

                self.workflows.append(workflow)
                if not workflow.has_tests():
                    continue

                workflow.instrument_os()
                workflow.instrument_strategy()
                workflow.instrument_setup_steps()
                workflow.instrument_test_steps()

                filename = os.path.basename(workflow.path)
                dirpath = os.path.dirname(workflow.path)
                new_filename = filename.split('.')[0] + "-crawler." + filename.split('.')[1]
                new_path = os.path.join(dirpath, new_filename)
                workflow.path = new_path

                self.test_workflows.append(workflow)
                
    def save_workflows(self):
        for workflow in self.test_workflows:
            if not os.path.exists(os.path.dirname(workflow.path)):
                os.makedirs(os.path.dirname(workflow.path))
            workflow.save_yaml(workflow.path)

    def delete_workflow(self, workflow):
        if os.path.exists(workflow.path):
            os.remove(workflow.path)

    def remove_workflow(self, rem_workflow):
        for i, workflow in enumerate(self.test_workflows):
            if rem_workflow.path == workflow.path:
                self.test_workflows.pop(i)
                self.delete_workflow(workflow)
                break

    def delete_workflows(self):
        for workflow in self.test_workflows:
            self.delete_workflow(workflow)

    def run_workflow(self, workflow) -> ActTestsRun:
        act = Act(False, timeout=10)
        return act.run_act(self.repo_path, workflow)
    
    def remove_containers(self):
        client = docker.from_env()
        ancestors = [
            "crawlergpt:latest", 
        ]

        for container in client.containers.list(filters={"ancestor": ancestors}):
            container.stop()
            container.remove()

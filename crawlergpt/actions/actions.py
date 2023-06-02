import os
import docker
import logging
import subprocess

from typing import List

from crawlergpt.actions.multi.testparser import TestParser
from crawlergpt.actions.multi.junitxmlparser import JUnitXMLParser
from crawlergpt.actions.java.maven_workflow import MavenWorkflow
from crawlergpt.actions.workflow import GitHubWorkflow

class Act:
    __ACT_PATH="act"
    __ACT_SETUP=False
    # The flag -u allows files to be created with the current user
    __FLAGS=f"--bind --pull=false --container-options '-u {os.getuid()}'"
    __DEFAULT_RUNNERS = "-P ubuntu-latest=crawlergpt:latest"
    
    
    def __init__(self, reuse, timeout=5):
        '''
        Args:
            timeout (int): Timeout in minutes
        '''
        if not Act.__ACT_SETUP:
            Act.__setup_act()

        if reuse:
            self.flags = "--reuse"
        else:
            self.flags = "--rm"
        self.timeout = timeout
        

    @staticmethod
    def __setup_act():
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
            dockerfile += f"RUN usermod -u {os.getuid()} runneradmin"
            f.write(dockerfile)

        client.images.build(path="./", tag="crawlergpt", forcerm=True)
        os.remove("Dockerfile")
    

    def run_act(self, repo_path, workflow: GitHubWorkflow):
        command = f"cd {repo_path}; "
        command += f"timeout {self.timeout * 60} {Act.__ACT_PATH} {Act.__DEFAULT_RUNNERS} {Act.__FLAGS} {self.flags}"
        command += f" -W {workflow}"

        run = subprocess.run(command, shell=True, capture_output=True)
        stdout = run.stdout.decode('utf-8')
        stderr = run.stderr.decode('utf-8')
        tests_failed = workflow.get_failed_tests(repo_path)
        if len(tests_failed) == 0 and run.returncode != 0:
            return None, stdout, stderr
        
        return tests_failed, stdout, stderr


class GitHubActions:
    """
    Class to handle GitHub Actions
    """
    
    def __init__(self, repo_path):
        self.repo_path = repo_path
        self.workflows = []
        self.test_workflows = []

        workflows_path = os.path.join(repo_path, ".github", "workflows")
        for (dirpath, dirnames, filenames) in os.walk(workflows_path):
            yaml_files = list(filter(lambda file: file.endswith('.yml') or file.endswith('.yaml'), filenames))
            for file in yaml_files:
                workflow = MavenWorkflow(os.path.join(dirpath, file))
                self.workflows.append(workflow)
                
                if not workflow.has_tests():
                    continue

                workflow.instrument_os()
                workflow.instrument_strategy()
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

    def run_workflow(self, workflow):
        act = Act(False, timeout=10)
        failed_tests, stdout, stderr = act.run_act(self.repo_path, workflow)
        return failed_tests, stdout, stderr
    
    def remove_containers(self):
        client = docker.from_env()
        ancestors = [
            "crawlergpt:latest", 
        ]

        for container in client.containers.list(filters={"ancestor": ancestors}):
            container.stop()
            container.remove()
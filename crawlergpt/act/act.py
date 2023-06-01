import os
import docker
import logging
import subprocess

from crawlergpt.act.parser.junitxmlparser import TestParser
from crawlergpt.act.workflow import GithubWorkflow

class Act:
    ACT_PATH="act"
    # The flag -u allows files to be created with the current user
    __FLAGS=f"--bind --pull=false --container-options '-u {os.getuid()}'"
    __DEFAULT_RUNNERS = "-P ubuntu-latest=crawlergpt:latest"
    
    def __init__(self, reuse, timeout=5):
        '''
        Args:
            timeout (int): Timeout in minutes
        '''
        if reuse:
            self.flags = "--reuse"
        else:
            self.flags = "--rm"
        self.timeout = timeout

    def run_act(self, repo_path, workflow, test_parser):
        command = f"cd {repo_path}; "
        command += f"timeout {self.timeout * 60} {Act.ACT_PATH} {Act.__DEFAULT_RUNNERS} {Act.__FLAGS} {self.flags}"
        command += f" -W {workflow}"

        run = subprocess.run(command, shell=True, capture_output=True)
        stdout = run.stdout.decode('utf-8')
        stderr = run.stderr.decode('utf-8')
        tests_failed = test_parser.get_failed_tests()
        if len(tests_failed) == 0 and run.returncode != 0:
            return None, stdout, stderr
        
        return tests_failed, stdout, stderr


class GitHubTestActions:
    def __init__(self, repo_path):
        self.repo_path = repo_path
        self.workflows = []
        self.test_workflows = []

        workflows_path = os.path.join(repo_path, ".github", "workflows")
        for (dirpath, dirnames, filenames) in os.walk(workflows_path):
            yaml_files = list(filter(lambda file: file.endswith('.yml') or file.endswith('.yaml'), filenames))
            for file in yaml_files:
                workflow = GithubWorkflow(os.path.join(dirpath, file))
                self.workflows.append(workflow)
                
                if not workflow.has_tests():
                    continue

                workflow.remove_unsupported_os()
                workflow.simplify_strategies()
                workflow.instrument_test_actions()

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

    def get_failed_tests(self, workflow):
        act = Act(False, timeout=10)
        # TODO look into the correct xml folder
        parser = TestParser(os.path.join(self.repo_path, "target", "surefire-reports"))
        workflow_rel_path = os.path.relpath(workflow.path, self.repo_path)
        failed_tests, stdout, stderr = act.run_act(self.repo_path, workflow_rel_path, parser)
        return failed_tests, stdout, stderr
    
    def remove_containers(self):
        client = docker.from_env()
        ancestors = [
            "crawlergpt:latest", 
        ]

        for container in client.containers.list(filters={"ancestor": ancestors}):
            container.stop()
            container.remove()

# Checks act installation
run = subprocess.run(f"{Act.ACT_PATH} --help", shell=True, capture_output=True)
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
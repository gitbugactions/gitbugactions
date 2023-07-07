import os, tempfile, shutil, traceback
import pygit2
import grp
import uuid
import time
import docker
import logging
import subprocess
import threading
from typing import List, Dict
from junitparser import TestCase, Error
from dataclasses import dataclass
from crawlergpt.actions.workflow import GitHubWorkflow, GitHubWorkflowFactory
from crawlergpt.github_token import GithubToken


class Action:
    # Class to represent a GitHub Action
    # Note: We consider only the major version of the action, thus we ignore the minor and patch versions

    def __init__(self, declaration: str):
        self.declaration = declaration
        self.name = self.__get_name()
        self.version = self.__get_version()

    def __get_name(self) -> str:
        return self.declaration.split("@")[0].strip()

    def __get_version(self) -> str:
        return self.declaration.split("@")[1].split(".")[0].strip()

    def download(self, cache_dir: str):
        # Download the action to the cache dir
        # The name of the diretory is in the format <espaced_action_name>@<action_version>
        action_dir = os.path.join(
            cache_dir, self.name.replace("/", "-") + "@" + self.version
        )

        # If the action is already in the cache, raise an exception
        if os.path.exists(action_dir):
            raise Exception(
                f"Action {self.name}@{self.version} is already in the cache"
            )

        try:
            # Clone the action to the action dir using pygit2
            repo = pygit2.clone_repository(
                f"https://github.com/{self.name}.git", action_dir
            )

            # Checkout the action version
            repo.checkout(f"refs/tags/{self.version}")
        except Exception:
            # If something goes wrong, delete the action dir
            shutil.rmtree(action_dir, ignore_errors=True)
            raise Exception(
                f"Error while downloading action {self.name}@{self.version}: {traceback.format_exc()}"
            )

    def __hash__(self) -> int:
        return hash((self.name, self.version))

    def __eq__(self, other):
        return self.name == other.name and self.version == other.version


class ActCacheDirManager:
    # We need to set a different cache dir for each worker to avoid conflicts
    # See https://github.com/nektos/act/issues/1885 -> "act's git actions download cache isn't process / thread safe"

    __ACT_CACHE_DIR_LOCK: threading.Lock = threading.Lock()
    __ACT_CACHE_DIRS: Dict[str, bool] = dict()
    __DEFAULT_CACHE_DIR: str = os.path.join(
        tempfile.gettempdir(), "act-cache", "default"
    )

    @classmethod
    def init_act_cache_dirs(cls, n_dirs: int):
        cls.__ACT_CACHE_DIR_LOCK.acquire()
        cls.__ACT_CACHE_DIRS = {
            os.path.join(tempfile.gettempdir(), "act-cache", str(uuid.uuid4())): True
            for _ in range(n_dirs)
        }
        cls.__ACT_CACHE_DIR_LOCK.release()

    @classmethod
    def acquire_act_cache_dir(cls) -> str:
        """
        A thread calls this method to acquire a free act cache dir from the queue
        """
        cls.__ACT_CACHE_DIR_LOCK.acquire()

        try:
            if len(cls.__ACT_CACHE_DIRS) == 0:
                logging.warning(
                    f"Using a default act cache dir. If running multiple threads you must use different act caches for each thread."
                )
                return cls.__DEFAULT_CACHE_DIR

            for cache_dir in cls.__ACT_CACHE_DIRS:
                if cls.__ACT_CACHE_DIRS[cache_dir]:
                    cls.__ACT_CACHE_DIRS[cache_dir] = False
                    return cache_dir

            logging.warning(f"No act cache dir is available. Using a random one...")

            return os.path.join(tempfile.gettempdir(), "act-cache", str(uuid.uuid4()))
        finally:
            cls.__ACT_CACHE_DIR_LOCK.release()

    @classmethod
    def return_act_cache_dir(cls, act_cache_dir: str):
        """
        A thread calls this method to return and free up the acquired act cache dir
        """
        cls.__ACT_CACHE_DIR_LOCK.acquire()

        try:
            # If the default cache dir, do nothing
            if act_cache_dir == cls.__DEFAULT_CACHE_DIR:
                return
            # If a managed one, make it free
            elif act_cache_dir in cls.__ACT_CACHE_DIRS:
                cls.__ACT_CACHE_DIRS[act_cache_dir] = True
                return
            # If a random one delete it
            elif os.path.exists(act_cache_dir):
                shutil.rmtree(act_cache_dir, ignore_errors=True)
                return
        finally:
            cls.__ACT_CACHE_DIR_LOCK.release()


@dataclass
class ActTestsRun:
    failed: bool
    tests: List[TestCase]
    stdout: str
    stderr: str
    workflow: GitHubWorkflow
    workflow_name: str
    build_tool: str
    elapsed_time: int

    @property
    def failed_tests(self):
        failed_tests = []
        for test in self.tests:
            # Check if it is failed (not passed, not skipped and without errors)
            if (
                not test.is_passed
                and not test.is_skipped
                and not any(map(lambda r: isinstance(r, Error), test.result))
            ):
                failed_tests.append(test)
        return failed_tests

    def asdict(self) -> Dict:
        res = {}

        for k, v in self.__dict__.items():
            if k == "tests":
                res[k] = []
                for test in self.tests:
                    results = []
                    for result in test.result:
                        results.append(
                            {
                                "result": result.__class__.__name__,
                                "message": result.message,
                                "type": result.type,
                            }
                        )
                    if len(results) == 0:
                        results.append({"result": "Passed", "message": "", "type": ""})

                    res[k].append(
                        {
                            "classname": test.classname,
                            "name": test.name,
                            "time": test.time,
                            "results": results,
                            "stdout": test.system_out,
                            "stderr": test.system_err,
                        }
                    )
            elif k == "workflow":
                res[k] = {
                    "path": self.workflow.path,
                    "type": self.workflow.get_build_tool(),
                }
            else:
                res[k] = v

        return res


class Act:
    __ACT_PATH = "act"
    __ACT_SETUP = False
    # The flag -u allows files to be created with the current user
    __FLAGS = f"--bind --pull=false --no-cache-server"
    __SETUP_LOCK = threading.Lock()

    def __init__(
        self, reuse, timeout=5, runner: str = "crawlergpt:latest", offline: bool = False
    ):
        """
        Args:
            timeout (int): Timeout in minutes
        """
        Act.__setup_act()
        if reuse:
            self.flags = "--reuse"
        else:
            self.flags = "--rm"

        self.flags += f" --container-options '-u {os.getuid()}:{os.getgid()}"
        if offline:
            self.flags += " --network none"
        self.flags += "'"

        self.__DEFAULT_RUNNERS = f"-P ubuntu-latest={runner}"
        self.timeout = timeout

    @staticmethod
    def __setup_act():
        Act.__SETUP_LOCK.acquire()
        if Act.__ACT_SETUP:
            Act.__SETUP_LOCK.release()
            return
        # Checks act installation
        run = subprocess.run(
            f"{Act.__ACT_PATH} --help", shell=True, capture_output=True
        )
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

    def run_act(
        self, repo_path, workflow: GitHubWorkflow, act_cache_dir: str
    ) -> ActTestsRun:
        command = f"cd {repo_path}; "
        command += f"XDG_CACHE_HOME='{act_cache_dir}' timeout {self.timeout * 60} {Act.__ACT_PATH} {self.__DEFAULT_RUNNERS} {Act.__FLAGS} {self.flags}"
        if GithubToken.has_tokens():
            token: GithubToken = GithubToken.get_token()
            command += f" -s GITHUB_TOKEN={token.token}"
        command += f" -W {workflow.path}"

        start_time = time.time()
        run = subprocess.run(command, shell=True, capture_output=True)
        end_time = time.time()
        stdout = run.stdout.decode("utf-8")
        stderr = run.stderr.decode("utf-8")
        tests = workflow.get_test_results(repo_path)
        tests_run = ActTestsRun(
            failed=False,
            tests=tests,
            stdout=stdout,
            stderr=stderr,
            workflow=workflow,
            workflow_name=workflow.doc["name"],
            build_tool=workflow.get_build_tool(),
            elapsed_time=end_time - start_time,
        )

        if len(tests_run.failed_tests) == 0 and run.returncode != 0:
            tests_run.failed = True

        updated_tokens = set()
        if GithubToken.has_tokens():
            token.update_rate_limit()
            updated_tokens.add(token.token)
            for token in workflow.tokens:
                if token.token not in updated_tokens:
                    token.update_rate_limit()

        return tests_run


class GitHubActions:
    """
    Class to handle GitHub Actions
    """

    def __init__(
        self,
        repo_path,
        language: str,
        keep_containers: bool = False,
        runner: str = "crawlergpt:latest",
        offline: bool = False,
    ):
        self.repo_path = repo_path
        self.keep_containers = keep_containers
        self.language: str = language.strip().lower()
        self.workflows: List[GitHubWorkflow] = []
        self.test_workflows: List[GitHubWorkflow] = []
        self.runner = runner
        self.offline = offline

        workflows_path = os.path.join(repo_path, ".github", "workflows")
        for dirpath, dirnames, filenames in os.walk(workflows_path):
            yaml_files = list(
                filter(
                    lambda file: file.endswith(".yml") or file.endswith(".yaml"),
                    filenames,
                )
            )
            for file in yaml_files:
                # Create workflow object according to the language and build system
                workflow = GitHubWorkflowFactory.create_workflow(
                    os.path.join(dirpath, file), self.language
                )

                self.workflows.append(workflow)
                if not workflow.has_tests():
                    continue

                workflow.instrument_os()
                workflow.instrument_strategy()
                workflow.instrument_setup_steps()
                workflow.instrument_test_steps()

                filename = os.path.basename(workflow.path)
                dirpath = os.path.dirname(workflow.path)
                new_filename = (
                    filename.split(".")[0] + "-crawler." + filename.split(".")[1]
                )
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

    def run_workflow(self, workflow, act_cache_dir: str) -> ActTestsRun:
        act = Act(
            self.keep_containers, timeout=10, runner=self.runner, offline=self.offline
        )
        return act.run_act(self.repo_path, workflow, act_cache_dir=act_cache_dir)

    def remove_containers(self):
        client = docker.from_env()
        ancestors = [
            "crawlergpt:latest",
        ]

        for container in client.containers.list(filters={"ancestor": ancestors}):
            container.stop()
            container.remove()

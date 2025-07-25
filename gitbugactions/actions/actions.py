import grp
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
import traceback
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Set

from junitparser import Error, TestCase

from gitbugactions.actions.action import Action
from gitbugactions.actions.workflow import GitHubWorkflow
from gitbugactions.actions.workflow_factory import GitHubWorkflowFactory
from gitbugactions.docker.client import DockerClient
from gitbugactions.github_api import GithubToken
from gitbugactions.utils.repo_state_manager import RepoStateManager


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
        with cls.__ACT_CACHE_DIR_LOCK:
            # Generate the directories
            cls.__ACT_CACHE_DIRS = {
                os.path.join(
                    tempfile.gettempdir(), "act-cache", str(uuid.uuid4())
                ): True
                for _ in range(n_dirs)
            }

            # Create the directories
            for cache_dir in cls.__ACT_CACHE_DIRS:
                if not os.path.exists(cache_dir):
                    os.makedirs(os.path.join(cache_dir, "act"))
            if not os.path.exists(cls.__DEFAULT_CACHE_DIR):
                os.makedirs(cls.__DEFAULT_CACHE_DIR)

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

    @classmethod
    def cache_action(cls, action: Action):
        """
        Downloads an action to the base cache dir and creates a symlink to it in every act cache dir
        Note: because every action is unique, we do not need locks here
        """
        try:
            # Download the action to the base cache dir
            # The name of the diretory is in the format <org>-<repo>@<ref>
            action_dir_name = f"{action.org}-{action.repo}@{action.ref}"
            action_dir = os.path.join(cls.__DEFAULT_CACHE_DIR, action_dir_name)
            action.download(action_dir)

            # Create a symlink to the action in every act cache dir
            for cache_dir in cls.__ACT_CACHE_DIRS:
                os.symlink(action_dir, os.path.join(cache_dir, "act", action_dir_name))
        except Exception:
            logging.error(
                f"Error while caching action {action.declaration}: {traceback.format_exc()}"
            )


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
    default_actions: bool
    return_code: int

    @property
    def failed_tests(self) -> List[TestCase]:
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

    @property
    def erroring_tests(self) -> List[TestCase]:
        erroring_tests = []
        for test in self.tests:
            # Check if it is erroring (not passed, not skipped, and with erorrs)
            if any(map(lambda r: isinstance(r, Error), test.result)):
                erroring_tests.append(test)
        return erroring_tests

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


class ActFailureStrategy(ABC):
    @abstractmethod
    def failed(self, tests_run: ActTestsRun) -> bool:
        pass


class ActTestsFailureStrategy(ActFailureStrategy):
    def failed(self, run: ActTestsRun) -> bool:
        return (
            # Failed run with failed tests but with memory limit exceed should not
            # be considered. We do not check the return code because act does not
            # pass the code from the container.
            run.return_code == 1  # Increase performance by avoiding
            and len(run.failed_tests) != 0  # to check the output in every run
            and (
                "exitcode '137'" in run.stderr
                or "exitcode '137': failure" in run.stdout
            )
        ) or (
            # 124 is the return code for the timeout
            (run.return_code == 124)
            or (len(run.failed_tests) == 0 and run.return_code != 0)
            or len(run.erroring_tests) > 0
        )


class ActCheckCodeFailureStrategy(ActFailureStrategy):
    def failed(self, run: ActTestsRun) -> bool:
        return run.return_code != 0


class Act:
    __ACT_PATH = "act"
    __ACT_CHECK = False
    __IMAGE_SETUP = False
    __FLAGS = f"--pull=false --no-cache-server --max-parallel 1"
    __SETUP_LOCK = threading.Lock()
    __MEMORY_LIMIT = "7g"
    # Default base image to build the runner image from if none specified
    __DEFAULT_BASE_IMAGE = "nunosaavedra/gitbug-actions:setup"
    # Image that is built locally with correct permissions set
    __DEFAULT_IMAGE = "gitbugactions:latest"

    def __init__(
        self,
        reuse: bool = False,
        timeout=5,
        runner_image: str = __DEFAULT_IMAGE,
        offline: bool = False,
        fail_strategy: ActFailureStrategy = ActTestsFailureStrategy(),
        base_image: str | None = None,
    ):
        """
        Args:
            timeout (int): Timeout in minutes
            runner_image (str): Name of the runner image to use
            offline (bool): Whether to run in offline mode
            fail_strategy (ActFailureStrategy): Strategy to determine test failures
            base_image (str): Base image to use for building the runner image. If None, uses default.
        """
        Act.__check_act()
        Act.__setup_image(runner_image, base_image)
        if reuse:
            self.flags = "--reuse"
        else:
            self.flags = "--rm"
        # The flag -u allows files to be created with the current user
        self.flags += f" --container-options '-u {os.getuid()}:{os.getgid()}"
        if offline:
            self.flags += " --network none"
        self.flags += f" --memory={Act.__MEMORY_LIMIT}"
        self.flags += "'"

        self.__DEFAULT_RUNNERS = f"-P ubuntu-latest={runner_image}"
        self.timeout = timeout
        self.fail_strategy = fail_strategy

    @staticmethod
    def __check_act():
        if Act.__ACT_CHECK:
            return

        run = subprocess.run(
            f"{Act.__ACT_PATH} --help", shell=True, capture_output=True
        )
        if run.returncode != 0:
            logging.error("Act is not correctly installed")
            exit(-1)
        Act.__ACT_CHECK = True

    @staticmethod
    def __setup_image(runner_image: str, base_image: str | None = None):
        with Act.__SETUP_LOCK:
            client = DockerClient.getInstance()
            if Act.__IMAGE_SETUP:
                return
            elif len(client.images.list(name=runner_image)) == 1:
                Act.__IMAGE_SETUP = True
                return
            elif runner_image != Act.__DEFAULT_IMAGE:
                logging.error(f"Base image {runner_image} does not exist")
                exit(-1)

            # Creates crawler image
            if len(client.images.list(name="gitbugactions")) > 0:
                client.images.remove(image="gitbugactions")

            base = base_image if base_image else Act.__DEFAULT_BASE_IMAGE
            with open("Dockerfile", "w") as f:
                client = DockerClient.getInstance()
                dockerfile = f"FROM {base}\n"
                dockerfile += f"RUN sudo usermod -u 4000000 runneradmin\n"
                dockerfile += f"RUN sudo groupadd -o -g {os.getgid()} {grp.getgrgid(os.getgid()).gr_name}\n"
                dockerfile += f"RUN sudo usermod -G {os.getgid()} runner\n"
                dockerfile += f"RUN sudo usermod -o -u {os.getuid()} runner\n"
                # Avoids problems with Rust projects in certain hosts
                dockerfile += f'ENV RUSTUP_HOME="/usr/share/rust/.rustup"\n'
                f.write(dockerfile)

            client.images.build(path="./", tag="gitbugactions", forcerm=True)
            os.remove("Dockerfile")
            Act.__IMAGE_SETUP = True

    @staticmethod
    def set_memory_limit(limit: str):
        Act.__MEMORY_LIMIT = limit

    def run_act(
        self, repo_path, workflow: GitHubWorkflow, act_cache_dir: str
    ) -> ActTestsRun:
        # Clean up before running
        RepoStateManager.clean_act_result_dir(repo_path)

        command = f"cd {repo_path}; "
        command += f"ACT_DISABLE_VERSION_CHECK=1 XDG_CACHE_HOME='{act_cache_dir}' timeout {self.timeout * 60} {Act.__ACT_PATH} {self.__DEFAULT_RUNNERS} {Act.__FLAGS} {self.flags}"
        if GithubToken.has_tokens():
            token: GithubToken = GithubToken.get_token()
            command += f" -s GITHUB_TOKEN={token.token}"
        command += f" -W {workflow.path}"

        logging.debug(f"Running command: {command}")
        start_time = time.time()
        run = subprocess.run(command, shell=True, capture_output=True)
        end_time = time.time()

        stdout = run.stdout.decode("utf-8")
        stderr = run.stderr.decode("utf-8")

        tests = workflow.get_test_results(
            os.path.join(
                repo_path, ".act-result", os.path.basename(os.path.normpath(repo_path))
            )
        )

        tests_run = ActTestsRun(
            failed=False,
            tests=tests,
            stdout=stdout,
            stderr=stderr,
            workflow=workflow,
            workflow_name=workflow.doc["name"],
            build_tool=workflow.get_build_tool(),
            elapsed_time=end_time - start_time,
            default_actions=False,
            return_code=run.returncode,
        )

        if self.fail_strategy.failed(tests_run):
            tests_run.failed = True
            logging.debug(f"RETURN CODE: {run.returncode}")
            logging.debug(f"STDOUT: {stdout}")
            logging.debug(f"STDERR: {stderr}")

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
        language: str | None,
        keep_containers: bool = False,
        runner_image: str = "gitbugactions:latest",
        offline: bool = False,
        base_image: str | None = None,
        instrument_workflows: bool = True,
    ):
        self.repo_path = repo_path
        self.keep_containers = keep_containers
        self.language: str = language.strip().lower() if language else ""
        self.workflows: List[GitHubWorkflow] = []
        self.test_workflows: List[GitHubWorkflow] = []
        self.runner_image = runner_image
        self.offline = offline
        self.base_image = base_image
        self.instrument_workflows = instrument_workflows
        workflows_path = os.path.join(repo_path, ".github", "workflows")
        for dirpath, dirnames, filenames in os.walk(workflows_path):
            yaml_files = list(
                filter(
                    lambda file: file.endswith(".yml") or file.endswith(".yaml"),
                    filenames,
                )
            )
            for file in yaml_files:
                # Skip the workflow if it is already instrumented
                if "gitbugactions-crawler" in file:
                    continue

                # Create workflow object according to the language and build system
                workflow: GitHubWorkflow = GitHubWorkflowFactory.create_workflow(
                    os.path.join(dirpath, file), self.language
                )

                self.workflows.append(workflow)
                if not workflow.has_tests():
                    continue

                if not self.instrument_workflows:
                    self.test_workflows.append(workflow)
                    continue

                workflow.instrument_jobs()
                if workflow.has_matrix_include_exclude():
                    continue

                workflow.instrument_os()
                workflow.instrument_on_events()
                workflow.instrument_strategy()
                workflow.instrument_cache_steps()
                workflow.instrument_setup_steps()
                workflow.instrument_test_steps(repo_clone=self.repo_path)
                if offline:
                    workflow.instrument_offline_execution()
                else:
                    workflow.instrument_online_execution()

                filename = os.path.basename(workflow.path)
                dirpath = os.path.dirname(workflow.path)
                new_filename = (
                    filename.split(".")[0]
                    + "-gitbugactions-crawler."
                    + filename.split(".")[1]
                )
                new_path = os.path.join(dirpath, new_filename)
                workflow.path = new_path

                self.test_workflows.append(workflow)

    def get_actions(self) -> Set[Action]:
        actions: Set[Action] = set()
        for workflow in self.test_workflows:
            actions.update(workflow.get_actions())
        return actions

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

    def run_workflow(
        self,
        workflow: GitHubWorkflow,
        act_cache_dir: str,
        act_fail_strategy: ActFailureStrategy = ActTestsFailureStrategy(),
        timeout: int = 10,
    ) -> ActTestsRun:
        # Clean up before running
        RepoStateManager.clean_act_result_dir(self.repo_path)

        act = Act(
            self.keep_containers,
            timeout=timeout,
            runner_image=self.runner_image,
            offline=self.offline,
            fail_strategy=act_fail_strategy,
            base_image=self.base_image,
        )
        return act.run_act(self.repo_path, workflow, act_cache_dir=act_cache_dir)

    def remove_containers(self):
        client = DockerClient.getInstance()
        ancestors = [
            "gitbugactions:latest",
        ]

        for container in client.containers.list(filters={"ancestor": ancestors}):
            container.stop()
            container.remove(v=True, force=True)

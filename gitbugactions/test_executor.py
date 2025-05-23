import copy
import os
import threading
import time
import uuid
from typing import List

import schedule
from pygit2 import Repository

from gitbugactions.actions.actions import ActTestsRun, GitHubActions
from gitbugactions.docker.client import DockerClient
from gitbugactions.utils.repo_state_manager import RepoStateManager
from gitbugactions.actions.templates.template_workflows import TemplateWorkflowManager


class TestExecutor:
    __CLEANUP = []
    __CLEANUP_ENABLED = True
    __CLEANUP_LOCK = threading.Lock()

    def __init__(
        self,
        repo_clone: Repository,
        language: str,
        act_cache_dir: str,
        default_actions: GitHubActions,
        runner_image: str = "gitbugactions:latest",
        base_image: str | None = None,
        instrument_workflows: bool = True,
    ):
        TestExecutor.__schedule_cleanup(runner_image)
        self.act_cache_dir = act_cache_dir
        self.repo_clone = repo_clone
        self.runner_image = runner_image
        self.base_image = base_image
        self.language = language
        # Note: these default actions may have different configuration options
        # such as paths, runners, etc.
        self.default_actions = default_actions
        self.first_commit = repo_clone.revparse_single("HEAD")
        self.instrument_workflows = instrument_workflows

    @staticmethod
    def __schedule_cleanup(runner_image):
        with TestExecutor.__CLEANUP_LOCK:
            if (
                runner_image in TestExecutor.__CLEANUP
                or not TestExecutor.__CLEANUP_ENABLED
            ):
                return

            docker = DockerClient.getInstance()

            def cleanup():
                for container in docker.containers.list(
                    all=True, filters={"ancestor": runner_image, "status": "exited"}
                ):
                    container.remove(force=True)

            docker = DockerClient.getInstance()
            schedule.every(1).minutes.do(cleanup)

            class ScheduleThread(threading.Thread):
                @classmethod
                def run(cls):
                    while threading.main_thread().is_alive():
                        schedule.run_pending()
                        time.sleep(1)

            ScheduleThread().start()
            TestExecutor.__CLEANUP.append(runner_image)

    @staticmethod
    def toggle_cleanup(enabled: bool):
        with TestExecutor.__CLEANUP_LOCK:
            if not enabled:
                schedule.clear()
                TestExecutor.__CLEANUP.clear()
            TestExecutor.__CLEANUP_ENABLED = enabled

    def reset_repo(self):
        RepoStateManager.reset_to_commit(self.repo_clone, self.first_commit.id)

    def run_tests(
        self,
        keep_containers: bool = False,
        offline: bool = False,
        timeout: int = 10,
    ) -> List[ActTestsRun]:
        act_runs: List[ActTestsRun] = []
        default_actions = False

        # Cleanup act result dir
        RepoStateManager.clean_act_result_dir(self.repo_clone.workdir)

        test_actions = GitHubActions(
            self.repo_clone.workdir,
            self.language,
            keep_containers=keep_containers,
            runner_image=self.runner_image,
            offline=offline,
            base_image=self.base_image,
            instrument_workflows=self.instrument_workflows,
        )

        if len(test_actions.test_workflows) == 0 and self.default_actions is not None:
            default_actions = True
            for workflow in self.default_actions.test_workflows:
                new_workflow = copy.copy(workflow)
                new_workflow.path = os.path.join(
                    self.repo_clone.workdir,
                    ".github/workflows",
                    os.path.basename(workflow.path),
                )
                test_actions.test_workflows.append(new_workflow)

        temp_workflow_path = None
        if len(test_actions.test_workflows) == 0:
            temp_workflow_path = TemplateWorkflowManager.create_temp_workflow(
                self.repo_clone.workdir, self.language
            )
            # Re-create the actions instance to include the template workflow
            test_actions = GitHubActions(
                self.repo_clone.workdir,
                self.language,
                keep_containers=keep_containers,
                runner_image=self.runner_image,
                offline=offline,
                base_image=self.base_image,
                instrument_workflows=self.instrument_workflows,
            )

        act_runs: List[ActTestsRun] = []

        # Act creates names for the containers by hashing the content of the workflows
        # To avoid conflicts between threads, we randomize the name
        for workflow in test_actions.test_workflows:
            workflow.doc["name"] = f"{workflow.doc['name']}-{str(uuid.uuid4())}"
        test_actions.save_workflows()

        for workflow in test_actions.test_workflows:
            act_runs.append(
                test_actions.run_workflow(workflow, self.act_cache_dir, timeout=timeout)
            )

        # Only delete the ones we have created
        if self.instrument_workflows:
            test_actions.delete_workflows()

            if temp_workflow_path:
                TemplateWorkflowManager.remove_temp_workflow(temp_workflow_path)

        for act_run in act_runs:
            act_run.default_actions = default_actions

        return act_runs

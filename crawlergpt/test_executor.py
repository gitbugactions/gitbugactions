import os, copy, uuid, logging, traceback
import pygit2, yaml
from crawlergpt.actions.actions import GitHubActions, ActTestsRun
from crawlergpt.actions.workflow import GitHubWorkflow
from pygit2 import Repository
from typing import List


class TestExecutor:
    def __init__(
        self,
        repo_clone: Repository,
        language: str,
        act_cache_dir: str,
        runner: str = "crawlergpt:latest",
        workflows: List[GitHubWorkflow] = None,
    ):
        self.act_cache_dir = act_cache_dir
        self.repo_clone = repo_clone
        self.runner = runner
        self.language = language
        self.workflows = workflows
        if self.workflows is None:
            self.__get_default_actions()

    def __get_default_actions(self):
        if len(list(self.repo_clone.references.iterator())) == 0:
            return
        self.first_commit = self.repo_clone.revparse_single(
            str(self.repo_clone.head.target)
        )

        for commit in self.repo_clone.walk(
            self.repo_clone.head.target,
            pygit2.GIT_SORT_TOPOLOGICAL | pygit2.GIT_SORT_REVERSE,
        ):
            self.repo_clone.checkout_tree(commit)
            self.repo_clone.set_head(commit.oid)
            try:
                actions = GitHubActions(
                    self.repo_clone.workdir, self.language, runner=self.runner
                )
                if len(actions.test_workflows) > 0:
                    self.default_actions = actions
                    break
            except yaml.YAMLError:
                logging.warning(
                    f"YAML error while parsing workflow (repo={self.repo_clone}, commit={commit.oid}): {traceback.format_exc()})"
                )
                continue

        self.repo_clone.reset(self.first_commit.oid, pygit2.GIT_RESET_HARD)

    def run_tests(
        self, keep_containers: bool = False, offline: bool = False
    ) -> List[ActTestsRun]:
        act_runs = []

        test_actions = GitHubActions(
            self.repo_clone.workdir,
            self.language,
            keep_containers=keep_containers,
            runner=self.runner,
            offline=offline,
        )
        if self.workflows is not None:
            test_actions.test_workflows = self.workflows
        else:
            if len(test_actions.test_workflows) == 0:
                for workflow in self.default_actions.test_workflows:
                    new_workflow = copy.copy(workflow)
                    new_workflow.path = os.path.join(
                        self.repo_clone.workdir,
                        ".github/workflows",
                        os.path.basename(workflow.path),
                    )
                    test_actions.test_workflows.append(new_workflow)
            # Act creates names for the containers by hashing the content of the workflows
            # To avoid conflicts between threads, we randomize the name
            for workflow in test_actions.test_workflows:
                workflow.doc["name"] = str(uuid.uuid4())
            test_actions.save_workflows()

        for workflow in test_actions.test_workflows:
            act_runs.append(test_actions.run_workflow(workflow, self.act_cache_dir))

        if self.workflows is None:
            test_actions.delete_workflows()

        return act_runs

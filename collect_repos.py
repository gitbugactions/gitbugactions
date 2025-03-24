import datetime
import fire
import json
import logging
import os
import sys
import tempfile
import traceback
import uuid

from pathlib import Path
from typing import Optional
from github import Repository

from gitbugactions.actions.actions import (
    Act,
    ActCacheDirManager,
    ActCheckCodeFailureStrategy,
    GitHubActions,
)
from gitbugactions.actions.templates.template_workflows import (
    TemplateWorkflowManager,
)
from gitbugactions.crawler import RepoCrawler, RepoStrategy
from gitbugactions.infra.infra_checkers import is_infra_file
from gitbugactions.utils.repo_utils import clone_repo, delete_repo_clone


def run_workflow(repo_path, workflow, act_cache_dir, language, base_image=None):
    """
    Common utility to run a GitHub Actions workflow

    Args:
        repo_path: Path to the repository
        workflow: Workflow to run
        act_cache_dir: Act cache directory
        language: Repository language
        base_image: Base image to use for building the runner

    Returns:
        ActTestsRun: Result of running the workflow
    """
    # Act creates names for the containers by hashing the content of the workflows
    # To avoid conflicts between threads, we randomize the name
    workflow.doc["name"] = str(uuid.uuid4())

    # Create the GitHub Actions runner
    actions = GitHubActions(repo_path, language, base_image=base_image)
    actions.save_workflows()

    # Run the workflow
    return actions.run_workflow(workflow, act_cache_dir=act_cache_dir)


class CollectReposStrategy(RepoStrategy):
    def __init__(self, data_path: str, use_template_workflows: bool = True):
        self.data_path = data_path
        self.uuid = str(uuid.uuid1())
        self.use_template_workflows = (
            use_template_workflows  # Flag to control template workflow usage
        )

    def save_data(self, data: dict, repo):
        """
        Saves the data json to a file with the name of the repository
        """
        repo_name = repo.full_name.replace("/", "-")
        data_path = os.path.join(self.data_path, repo_name + ".json")
        with open(data_path, "w") as f:
            json.dump(data, f, indent=4)

    def handle_repo(self, repo: Repository):
        logging.info(f"Cloning {repo.full_name} - {repo.clone_url}")
        repo_path = os.path.join(
            tempfile.gettempdir(), self.uuid, repo.full_name.replace("/", "-")
        )

        # Handle repositories without a language detected
        if repo.language is None:
            logging.info(f"Skipping {repo.full_name} - no language detected")
            return

        data = {
            "repository": repo.full_name,
            "stars": repo.stargazers_count,
            "language": repo.language.strip().lower(),
            "size": repo.size,
            "clone_url": repo.clone_url,
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat() + "Z",
            "clone_success": False,
            "number_of_actions": 0,
            "number_of_test_actions": 0,
            "actions_successful": False,
            "using_template_workflow": False,  # Track if we used a template workflow
        }

        repo_clone = clone_repo(repo.clone_url, repo_path)

        try:
            data["clone_success"] = True

            actions = GitHubActions(repo_path, repo.language)
            data["number_of_actions"] = len(actions.workflows)
            data["actions_build_tools"] = [
                x.get_build_tool() for x in actions.workflows
            ]
            data["number_of_test_actions"] = len(actions.test_workflows)
            data["actions_test_build_tools"] = [
                x.get_build_tool() for x in actions.test_workflows
            ]
            actions.save_workflows()

            # Check if we have test workflows, otherwise use a template if enabled
            if len(actions.test_workflows) == 0 and self.use_template_workflows:
                logging.info(
                    f"No test workflows found, creating template for {repo.full_name}"
                )

                # Use the context manager to automatically handle cleanup
                with TemplateWorkflowManager.create_temp_workflow(
                    repo_path, repo.language
                ) as template_path:
                    if template_path:
                        # Create a new actions instance to include our template
                        actions = GitHubActions(repo_path, repo.language)
                        data["using_template_workflow"] = True
                        actions.save_workflows()

                        # Now run the template workflow
                        if len(actions.test_workflows) == 1:
                            logging.info(
                                f"Running template workflow for {repo.full_name}"
                            )

                            act_cache_dir = ActCacheDirManager.acquire_act_cache_dir()
                            try:
                                act_run = run_workflow(
                                    repo_path,
                                    actions.test_workflows[0],
                                    act_cache_dir,
                                    repo.language,
                                )
                                data["actions_successful"] = not act_run.failed
                                data["actions_run"] = act_run.asdict()
                            finally:
                                ActCacheDirManager.return_act_cache_dir(act_cache_dir)

            # If no template was used but we have a test workflow, run it
            elif len(actions.test_workflows) == 1:
                logging.info(f"Running actions for {repo.full_name}")

                act_cache_dir = ActCacheDirManager.acquire_act_cache_dir()
                try:
                    act_run = run_workflow(
                        repo_path,
                        actions.test_workflows[0],
                        act_cache_dir,
                        repo.language,
                    )
                    data["actions_successful"] = not act_run.failed
                    data["actions_run"] = act_run.asdict()
                finally:
                    ActCacheDirManager.return_act_cache_dir(act_cache_dir)

            delete_repo_clone(repo_clone)
            self.save_data(data, repo)
        except Exception as e:
            logging.error(
                f"Error while processing {repo.full_name}: {traceback.format_exc()}"
            )

            delete_repo_clone(repo_clone)
            self.save_data(data, repo)


class CollectInfraReposStrategy(CollectReposStrategy):
    def __init__(self, data_path: str, use_template_workflows: bool = False):
        super().__init__(data_path, use_template_workflows)
        if use_template_workflows:
            logging.warning("use_template_workflows is not supported for infra repos")

    def test_actions(self, data: dict, repo: Repository, repo_path: str):
        actions = GitHubActions(repo_path, repo.language)
        data["number_of_actions"] = len(actions.workflows)
        data["actions_build_tools"] = [x.get_build_tool() for x in actions.workflows]
        data["number_of_test_actions"] = len(actions.test_workflows)
        data["actions_test_build_tools"] = [
            x.get_build_tool() for x in actions.test_workflows
        ]
        data["actions_run"] = []
        actions.save_workflows()

        if len(actions.workflows) >= 1:
            logging.info(f"Running actions for {repo.full_name}")

            for workflow in actions.workflows:
                # Act creates names for the containers by hashing the content of the workflows
                # To avoid conflicts between threads, we randomize the name
                workflow.doc["name"] = str(uuid.uuid4())
                actions.save_workflows()

                act_cache_dir = ActCacheDirManager.acquire_act_cache_dir()
                try:
                    act_run = actions.run_workflow(
                        workflow,
                        act_cache_dir=act_cache_dir,
                        act_fail_strategy=ActCheckCodeFailureStrategy(),
                    )
                finally:
                    ActCacheDirManager.return_act_cache_dir(act_cache_dir)

                data["actions_run"].append(act_run.asdict())
                if not act_run.failed:
                    data["actions_successful"] = True
                    break
            else:
                data["actions_successful"] = False

    def handle_repo(self, repo: Repository):
        logging.info(f"Cloning {repo.full_name} - {repo.clone_url}")
        repo_path = os.path.join(
            tempfile.gettempdir(), self.uuid, repo.full_name.replace("/", "-")
        )

        data = {
            "repository": repo.full_name,
            "stars": repo.stargazers_count,
            "language": (
                repo.language.strip().lower() if repo.language is not None else ""
            ),
            "size": repo.size,
            "clone_url": repo.clone_url,
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat() + "Z",
            "clone_success": False,
            "number_of_actions": -1,
            "number_of_test_actions": -1,
            "actions_successful": None,
        }

        repo_clone = clone_repo(repo.clone_url, repo_path)
        data["clone_success"] = True

        infra_files = 0
        for root, _, files in os.walk(repo_path):
            for f in files:
                if is_infra_file(Path(os.path.join(root, f))):
                    infra_files += 1

        data["infra_files"] = infra_files
        if infra_files == 0:
            delete_repo_clone(repo_clone)
            self.save_data(data, repo)
            return

        try:
            self.test_actions(data, repo, repo_path)
            delete_repo_clone(repo_clone)
            self.save_data(data, repo)
        except Exception as e:
            logging.error(
                f"Error while processing {repo.full_name}: {traceback.format_exc()}"
            )

            delete_repo_clone(repo_clone)
            self.save_data(data, repo)


def collect_repos(
    query: str,
    pagination_freq: Optional[str] = None,
    n_workers: int = 1,
    out_path: str = "./out/",
    base_image: str | None = None,
    use_template_workflows: bool = True,
):
    """Collect the repositories from GitHub that match the query and have executable
    GitHub Actions workflows with parsable tests.

    Args:
        query (str): Query with the Github searching format (https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories).
        pagination_freq (str, optional): Useful if the number of repos to collect is superior to 1000 results (GitHub limit). The possible values are listed here: https://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html#timeseries-offset-aliases.
                                         For instance, if the value is 'D', each request will be limited to the repos created in a single day, until all the days are obtained.
        n_workers (int, optional): Number of parallel workers. Defaults to 1.
        out_path (str, optional): Folder on which the results will be saved. Defaults to "./out/".
        base_image (str, optional): Base image to use for building the runner image. If None, uses default.
        use_template_workflows (bool, optional): Whether to use template workflows for repos without test workflows. Defaults to True.
    """
    if not Path(out_path).exists():
        os.makedirs(out_path, exist_ok=True)

    Act(base_image=base_image)  # Initialize Act with base_image
    crawler = RepoCrawler(query, pagination_freq=pagination_freq, n_workers=n_workers)
    crawler.get_repos(CollectReposStrategy(out_path, use_template_workflows))


def main():
    fire.Fire(collect_repos)


if __name__ == "__main__":
    sys.exit(main())

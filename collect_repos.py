import tempfile
import os, logging, sys, traceback
import json
import uuid
import fire
import datetime
from github import Repository
from pathlib import Path
from gitbugactions.util import delete_repo_clone, clone_repo
from gitbugactions.crawler import RepoStrategy, RepoCrawler
from gitbugactions.actions.actions import (
    GitHubActions,
    ActCacheDirManager,
    ActCheckCodeFailureStrategy,
)
from gitbugactions.infra.infra_checkers import is_infra_file


class CollectReposStrategy(RepoStrategy):
    def __init__(self, data_path: str):
        self.data_path = data_path
        self.uuid = str(uuid.uuid1())

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

            if len(actions.test_workflows) == 1:
                logging.info(f"Running actions for {repo.full_name}")

                # Act creates names for the containers by hashing the content of the workflows
                # To avoid conflicts between threads, we randomize the name
                actions.test_workflows[0].doc["name"] = str(uuid.uuid4())
                actions.save_workflows()

                act_cache_dir = ActCacheDirManager.acquire_act_cache_dir()
                try:
                    act_run = actions.run_workflow(
                        actions.test_workflows[0], act_cache_dir=act_cache_dir
                    )
                finally:
                    ActCacheDirManager.return_act_cache_dir(act_cache_dir)

                data["actions_successful"] = not act_run.failed
                data["actions_run"] = act_run.asdict()

            delete_repo_clone(repo_clone)
            self.save_data(data, repo)
        except Exception as e:
            logging.error(
                f"Error while processing {repo.full_name}: {traceback.format_exc()}"
            )

            delete_repo_clone(repo_clone)
            self.save_data(data, repo)


class CollectInfraReposStrategy(CollectReposStrategy):
    def __init__(self, data_path: str):
        super().__init__(data_path)

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
    query: str, pagination_freq: str = "M", n_workers: int = 1, out_path: str = "./out/"
):
    """Collect the repositories from GitHub that match the query and have executable
    GitHub Actions workflows with parsable tests.

    Args:
        query (str): Query with the Github searching format (https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories).
        pagination_freq (str, optional): Useful if the number of repos to collect is superior to 1000 results (GitHub limit). The possible values are listed here: https://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html#timeseries-offset-aliases.
                                         For instance, if the value is 'D', each request will be limited to the repos created in a single day, until all the days are obtained.
        n_workers (int, optional): Number of parallel workers. Defaults to 1.
        out_path (str, optional): Folder on which the results will be saved. Defaults to "./out/".
    """
    crawler = RepoCrawler(query, pagination_freq=pagination_freq, n_workers=n_workers)
    crawler.get_repos(CollectReposStrategy(out_path))


def main():
    fire.Fire(collect_repos)


if __name__ == "__main__":
    sys.exit(main())

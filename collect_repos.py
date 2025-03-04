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
from typing import Dict, List, Optional

from github import Repository

from gitbugactions.commit_execution.executor import CommitExecutor
from gitbugactions.actions.actions import ActCheckCodeFailureStrategy
from gitbugactions.crawler import RepoCrawler, RepoStrategy
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
        logging.info(f"Processing {repo.full_name} - {repo.clone_url}")
        
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
            "has_tests": False,
            "number_of_actions": 0,
            "number_of_test_actions": 0,
            "actions_successful": False,
            "actions_build_tools": [],
            "actions_test_build_tools": [],
            "infra_files": 0,
            "test_results": [],
            "execution_time": 0,
            "success": False,
            "error": None,
        }
        
        executor = None
        
        try:
            # Create a temporary directory for cloning
            with tempfile.TemporaryDirectory() as temp_dir:
                # Create a CommitExecutor
                executor = CommitExecutor(
                    repo_url=repo.clone_url,
                    work_dir=temp_dir,
                    timeout=3600,  # 1 hour timeout
                    custom_image=None,  # Use default image
                    offline_mode=False,
                )
                
                # Get the latest commit SHA
                latest_commit = self._get_latest_commit(executor)
                if not latest_commit:
                    data["error"] = "Failed to get latest commit"
                    return self.save_data(data, repo)
                
                # Get workflow information without executing tests
                try:
                    workflow_info = executor.get_workflow_info_at_commit(latest_commit)
                    all_workflows = workflow_info.get("all_workflows", [])
                    test_workflows = workflow_info.get("test_workflows", [])
                    all_build_tools = workflow_info.get("all_build_tools", [])
                    test_build_tools = workflow_info.get("test_build_tools", [])
                    
                    data["number_of_actions"] = len(all_workflows)
                    data["number_of_test_actions"] = len(test_workflows)
                    data["has_tests"] = len(test_workflows) > 0
                    data["clone_success"] = True
                    data["actions_build_tools"] = all_build_tools
                    data["actions_test_build_tools"] = test_build_tools
                    
                    # If no test workflows, we're done
                    if not data["has_tests"]:
                        logging.info(f"No test workflows found for {repo.full_name}")
                        return self.save_data(data, repo)
                    
                    # Execute tests at the latest commit
                    result = executor.execute_at_commit(latest_commit)
                    
                    # Update data with execution results
                    data["success"] = result.success
                    data["actions_successful"] = result.success
                    data["execution_time"] = result.execution_time
                    
                    # Format test results for backward compatibility
                    test_results = []
                    for test in result.test_results:
                        test_results.append({
                            "classname": test.classname,
                            "name": test.name,
                            "time": test.time,
                            "results": [
                                {
                                    "result": "Passed" if test.success else "Failed",
                                    "message": test.message or "",
                                    "type": ""
                                }
                            ],
                            "stdout": test.stdout,
                            "stderr": test.stderr
                        })
                    
                    # Create actions_run structure for backward compatibility
                    data["actions_run"] = {
                        "failed": not result.success,
                        "tests": test_results,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "workflow": {
                            "path": result.workflows_executed[0] if result.workflows_executed else "",
                            "type": result.all_build_tools[0] if result.all_build_tools else ""
                        },
                        "workflow_name": "",  # We don't have this information directly
                        "build_tool": result.all_build_tools[0] if result.all_build_tools else "",
                        "elapsed_time": result.execution_time,
                        "default_actions": False,
                        "return_code": 0 if result.success else 1
                    }
                    
                except Exception as e:
                    logging.error(f"Error executing tests: {str(e)}")
                    data["error"] = str(e)
            
            self.save_data(data, repo)
        except Exception as e:
            logging.error(
                f"Error while processing {repo.full_name}: {traceback.format_exc()}"
            )
            self.save_data(data, repo)
        finally:
            # Clean up resources
            if executor:
                executor.cleanup()

    def _get_latest_commit(self, executor) -> str:
        """Get the latest commit SHA from the repository."""
        try:
            # This is a bit of a hack, but we can access the repo_clone directly
            # to get the latest commit SHA
            if hasattr(executor, 'repo_clone') and executor.repo_clone:
                head = executor.repo_clone.head
                if head:
                    return str(head.target)
        except Exception as e:
            logging.error(f"Error getting latest commit: {str(e)}")
        return None


class CollectInfraReposStrategy(CollectReposStrategy):
    def __init__(self, data_path: str):
        super().__init__(data_path)

    def handle_repo(self, repo: Repository):
        logging.info(f"Processing {repo.full_name} - {repo.clone_url}")

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
            "has_tests": False,
            "number_of_actions": 0,
            "number_of_test_actions": 0,
            "actions_successful": False,
            "actions_build_tools": [],
            "actions_test_build_tools": [],
            "infra_files": 0,
            "error": None,
        }
        
        executor = None
        
        try:
            # Create a temporary directory for cloning
            with tempfile.TemporaryDirectory() as temp_dir:
                # Create a CommitExecutor
                executor = CommitExecutor(
                    repo_url=repo.clone_url,
                    work_dir=temp_dir,
                    timeout=3600,  # 1 hour timeout
                    custom_image=None,  # Use default image
                    offline_mode=False,
                )
                
                # Get the latest commit SHA
                latest_commit = self._get_latest_commit(executor)
                if not latest_commit:
                    data["error"] = "Failed to get latest commit"
                    return self.save_data(data, repo)
                
                # Count infrastructure files
                infra_files = 0
                repo_path = executor.repo_path
                for root, _, files in os.walk(repo_path):
                    for f in files:
                        file_path = Path(os.path.join(root, f))
                        if is_infra_file(file_path):
                            infra_files += 1
                
                data["infra_files"] = infra_files
                data["clone_success"] = True
                
                # If no infrastructure files, we're done
                if infra_files == 0:
                    logging.info(f"No infrastructure files found for {repo.full_name}")
                    return self.save_data(data, repo)
                
                # Get workflow information without executing tests
                try:
                    workflow_info = executor.get_workflow_info_at_commit(latest_commit)
                    all_workflows = workflow_info.get("all_workflows", [])
                    test_workflows = workflow_info.get("test_workflows", [])
                    all_build_tools = workflow_info.get("all_build_tools", [])
                    test_build_tools = workflow_info.get("test_build_tools", [])
                    
                    data["number_of_actions"] = len(all_workflows)
                    data["number_of_test_actions"] = len(test_workflows)
                    data["has_tests"] = len(test_workflows) > 0
                    data["clone_success"] = True
                    data["actions_build_tools"] = all_build_tools
                    data["actions_test_build_tools"] = test_build_tools
                    
                    # For infrastructure repos, we don't execute tests
                    logging.info(f"Found {len(all_workflows)} workflows for {repo.full_name}")
                    
                except Exception as e:
                    logging.error(f"Error getting workflow information: {str(e)}")
                    data["error"] = str(e)
            
            self.save_data(data, repo)
        except Exception as e:
            logging.error(
                f"Error while processing {repo.full_name}: {traceback.format_exc()}"
            )
            self.save_data(data, repo)
        finally:
            # Clean up resources
            if executor:
                executor.cleanup()


def collect_repos(
    query: str,
    pagination_freq: Optional[str] = None,
    n_workers: int = 1,
    out_path: str = "./out/",
    base_image: str | None = None,
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
    """
    if not Path(out_path).exists():
        os.makedirs(out_path, exist_ok=True)

    # Initialize the crawler and start collecting repos
    crawler = RepoCrawler(query, pagination_freq=pagination_freq, n_workers=n_workers)
    crawler.get_repos(CollectReposStrategy(out_path))


def main():
    fire.Fire(collect_repos)


if __name__ == "__main__":
    sys.exit(main())

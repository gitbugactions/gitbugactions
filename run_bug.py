import os
import sys
import json
import shutil
import fire
import pygit2
import uuid
import logging
from typing import Dict
from gitbugactions.test_executor import TestExecutor
from gitbugactions.docker.export import create_diff_image
from gitbugactions.docker.client import DockerClient
from gitbugactions.actions.workflow import GitHubWorkflowFactory
from gitbugactions.actions.actions import ActCacheDirManager, GitHubActions


def get_bug_from_metadata(metadata_path, repo_name, commit):
    res_bug = None
    metadata_file_path = os.path.join(metadata_path, f"{repo_name}.json")

    with open(metadata_file_path, "r") as f:
        lines = f.readlines()
        for line in lines:
            bug = json.loads(line)
            if bug["commit_hash"] == commit:
                res_bug = bug
                break

    return res_bug


def get_default_actions(diff_folder_path, repo_clone, language) -> GitHubActions:
    workflow_dir_path = os.path.join(diff_folder_path, "workflow")
    workflow_name = os.listdir(workflow_dir_path)[0]
    workflow_path = os.path.join(workflow_dir_path, workflow_name)

    github_actions_path = os.path.join(repo_clone.workdir, ".github", "workflows")
    if not os.path.exists(github_actions_path):
        os.makedirs(github_actions_path)
    new_workflow_path = os.path.join(github_actions_path, str(uuid.uuid4()) + ".yml")
    shutil.copyfile(workflow_path, new_workflow_path)

    workflows = [GitHubWorkflowFactory.create_workflow(new_workflow_path, language)]

    default_actions = GitHubActions(repo_clone.workdir, language)
    default_actions.test_workflows = workflows
    os.remove(new_workflow_path)

    return default_actions


def get_diff_path(diff_folder_path):
    for path in os.listdir(diff_folder_path):
        if path != "workflow":
            return os.path.join(diff_folder_path, path)


def run_bug(
    repo_name: str,
    commit: str,
    repo_clone_path: str,
    metadata_path: str,
    exported_path: str,
    offline: bool = False,
    bug: Dict = None,
):
    repo_name = repo_name.replace("/", "-")
    if bug is None:
        bug = get_bug_from_metadata(metadata_path, repo_name, commit)
    if bug is None:
        logging.error(f"{repo_name}@{commit} not found on the metadata folder.")
        exit(-1)

    repo_clone = pygit2.Repository(os.path.join(repo_clone_path, ".git"))
    diff_folder_path = os.path.join(exported_path, repo_name, commit)
    docker_client = DockerClient.getInstance()

    act_cache_dir = ActCacheDirManager.acquire_act_cache_dir()
    try:
        image_name = f"gitbugactions-run-bug:{str(uuid.uuid4())}"
        create_diff_image(
            "gitbugactions:latest", image_name, get_diff_path(diff_folder_path)
        )
        executor = TestExecutor(
            repo_clone,
            bug["language"],
            act_cache_dir,
            get_default_actions(diff_folder_path, repo_clone, bug["language"]),
            runner_image=image_name,
        )
        runs = executor.run_tests(offline=offline)
        docker_client.images.remove(image_name)
    finally:
        ActCacheDirManager.return_act_cache_dir(act_cache_dir)

    return runs


def main():
    fire.Fire(run_bug)


if __name__ == "__main__":
    sys.exit(main())

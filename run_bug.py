import os
import sys
import json
import shutil
import fire
import pygit2
import uuid
import docker
import logging
import tempfile
from crawlergpt.test_executor import TestExecutor
from crawlergpt.docker.export import create_diff_image
from crawlergpt.actions.workflow import GitHubWorkflowFactory


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


def run_bug(
    repo_name: str,
    commit: str,
    repo_clone_path: str,
    metadata_path: str,
    exported_path: str,
    offline: bool = False,
    previous_commit: bool = False,
):
    repo_name = repo_name.replace("/", "-")
    bug = get_bug_from_metadata(metadata_path, repo_name, commit)
    if bug is None:
        print(f"{repo_name}@{commit} not found on the metadata folder.")
        sys.stdout.flush()
        sys.stderr.flush()
        exit(-1)
    if previous_commit:
        commit = bug["previous_commit_hash"]

    repo_clone = pygit2.Repository(os.path.join(repo_clone_path, ".git"))
    diff_folder_path = os.path.join(exported_path, repo_name, commit)
    docker_client = docker.from_env()

    for path in os.listdir(diff_folder_path):
        if path != "workflow":
            image_name = f"crawlergpt-run-bug:{str(uuid.uuid4())}"
            create_diff_image(
                "crawlergpt:latest", image_name, os.path.join(diff_folder_path, path)
            )
            act_cache_dir = os.path.join(
                tempfile.gettempdir(), "act-cache", str(uuid.uuid4())
            )
            workflow_dir_path = os.path.join(diff_folder_path, "workflow")
            workflow_name = os.listdir(workflow_dir_path)[0]
            workflow_path = os.path.join(workflow_dir_path, workflow_name)

            github_actions_path = os.path.join(
                repo_clone.workdir, ".github", "workflows"
            )
            if not os.path.exists(github_actions_path):
                os.makedirs(github_actions_path)
            new_workflow_path = os.path.join(github_actions_path, workflow_name)
            shutil.copyfile(workflow_path, new_workflow_path)

            workflows = [
                GitHubWorkflowFactory.create_workflow(
                    new_workflow_path, bug["language"]
                )
            ]
            workflows[0].instrument_offline_execution()
            workflows[0].save_yaml(new_workflow_path)
            executor = TestExecutor(
                repo_clone,
                bug["language"],
                act_cache_dir,
                runner=image_name,
                workflows=workflows,
            )
            runs = executor.run_tests(offline=offline)
            os.remove(new_workflow_path)
            docker_client.images.remove(image_name)

            return runs

    print(f"{repo_name}@{commit} was not able to run.")
    sys.stdout.flush()
    sys.stderr.flush()
    exit(-1)


def main():
    fire.Fire(run_bug)


if __name__ == "__main__":
    sys.exit(main())

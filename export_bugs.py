import os
import sys
import yaml
import fire
import uuid
import json
import tqdm
import logging
import threading
import tempfile
import traceback
from docker.models.containers import Container
from typing import List, Dict
from gitbugactions.test_executor import TestExecutor
from gitbugactions.util import delete_repo_clone, get_default_github_actions, clone_repo
from gitbugactions.docker.export import extract_diff
from gitbugactions.docker.client import DockerClient
from concurrent.futures import ThreadPoolExecutor, as_completed
from gitbugactions.actions.actions import ActCacheDirManager, ActTestsRun
from collect_bugs import BugPatch

diff_file_lock = threading.Lock()


def create_exported_containers(
    repo_full_name: str,
    runs: List[ActTestsRun],
    bug_patch: BugPatch,
    export_commit: str,
    export_path: str,
):
    commit_hash = bug_patch.commit
    docker_client = DockerClient.getInstance()

    for run in runs:
        filters = {"name": f"act-{run.workflow_name}"}
        containers: List[Container] = docker_client.containers.list(filters=filters)
        if run.failed:
            logging.error(
                f"Run failed while exporting container {export_commit} from {repo_full_name}@{commit_hash} ({run.workflow_name}).\n"
                "Run stdout:\n"
                f"{run.stdout}\n\n"
                "Run stderr:\n"
                f"{run.stderr}"
            )

            for container in containers:
                container.stop()
                container.remove(v=True, force=True)
            exit(-1)

        for container in containers:
            container.stop()
            diff_folder_path = os.path.join(
                export_path, repo_full_name.replace("/", "-"), export_commit
            )
            with diff_file_lock:
                if not os.path.exists(diff_folder_path):
                    os.makedirs(diff_folder_path)
                else:
                    # Container already being saved. This may happen if bugs
                    # were collected from two consecutive commits
                    container.remove(v=True, force=True)
                    continue
            diff_file_path = os.path.join(diff_folder_path, container.name)
            extract_diff(container.id, diff_file_path, ignore_paths=["/tmp"])
            container.remove(v=True, force=True)

            workflows = os.path.join(diff_folder_path, "workflow")
            os.mkdir(workflows)
            with open(os.path.join(workflows, f"{run.workflow_name}.yml"), "w") as f:
                yaml.dump(run.workflow.doc, f)
        # FIXME: we only consider a single workflow per commit
        break


def export_bug_containers(bug: Dict, export_path: str):
    TestExecutor.toggle_cleanup(False)
    repo_full_name = bug["repository"]
    commit_hash = bug["commit_hash"]
    logging.info(f"Exporting {commit_hash} from {repo_full_name}...")
    temp_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
    repo_clone = clone_repo(f"https://github.com/{repo_full_name}", temp_path)
    first_commit = repo_clone.revparse_single(str(repo_clone.head.target))
    default_actions = get_default_github_actions(
        repo_clone, first_commit, bug["language"]
    )

    act_cache_dir = ActCacheDirManager.acquire_act_cache_dir()
    bug_patch: BugPatch = BugPatch.from_dict(bug, repo_clone)
    try:
        executor = TestExecutor(
            repo_clone, bug["language"], act_cache_dir, default_actions
        )
        runs = bug_patch.test_current_commit(executor, keep_containers=True)
        create_exported_containers(
            repo_full_name, runs, bug_patch, bug["commit_hash"], export_path
        )
    finally:
        ActCacheDirManager.return_act_cache_dir(act_cache_dir)
        delete_repo_clone(repo_clone)


def export_bugs(dataset_path: str, output_folder_path: str, n_workers=1):
    """Export the containers (reproducible environment) for the bug-fixes collected by collect_bugs.

    Args:
        dataset_path (str): Folder where the result of collect_bugs is.
        output_folder_path (str): Folder on which the results will be saved.
        n_workers (int, optional): Number of parallel workers. Defaults to 1.
    """
    ActCacheDirManager.init_act_cache_dirs(n_dirs=n_workers)
    executor = ThreadPoolExecutor(max_workers=n_workers)
    futures = []
    futures_to_bug = {}

    for jsonl_path in os.listdir(dataset_path):
        if jsonl_path == "log.out" or jsonl_path == "data.json":
            continue

        with open(os.path.join(dataset_path, jsonl_path), "r") as jsonl:
            lines = jsonl.readlines()
            for line in lines:
                bug = json.loads(line)
                futures.append(
                    executor.submit(export_bug_containers, bug, output_folder_path)
                )
                futures_to_bug[futures[-1]] = bug

    for future in tqdm.tqdm(as_completed(futures)):
        try:
            future.result()
        except Exception as e:
            print(
                f"Got an exception on bug {futures_to_bug[future]['repository']}@{futures_to_bug[future]['commit_hash']}: {traceback.format_exc()}"
            )
            continue

    executor.shutdown()


def main():
    fire.Fire(export_bugs)


if __name__ == "__main__":
    sys.exit(main())

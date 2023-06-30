import os
import sys
import yaml
import shutil
import fire
import uuid
import json
import pygit2
import docker
import logging
import subprocess
import threading
import tempfile
from docker.models.containers import Container
from typing import List, Dict
from crawlergpt.test_executor import TestExecutor
from crawlergpt.util import delete_repo_clone
from crawlergpt.docker.export import extract_diff
from concurrent.futures import ThreadPoolExecutor, as_completed

diff_file_lock = threading.Lock()

def export_bug_containers(bug: Dict, export_path: str):
    repo_full_name = bug['repository']
    commit_hash = bug['commit_hash']
    logging.info(f"Exporting {commit_hash} from {repo_full_name}...")
    temp_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
    repo_clone = pygit2.clone_repository(f"https://github.com/{repo_full_name}", temp_path)
    main_commit = repo_clone.revparse_single(str(repo_clone.head.target))
    # We need to set a different cache dir for each worker to avoid conflicts
    # See https://github.com/nektos/act/issues/1885 -> "act's git actions download cache isn't process / thread safe"
    act_cache_dir = os.path.join(tempfile.gettempdir(), "act-cache", str(uuid.uuid4()))
    executor = TestExecutor(repo_clone, bug['language'], act_cache_dir)
    commit: pygit2.Commit = repo_clone.revparse_single(commit_hash)
    previous_commit: pygit2.Commit = repo_clone.revparse_single(commit_hash + "~1")

    try:
        for c in [commit, previous_commit]:
            repo_clone.checkout_tree(c)
            repo_clone.set_head(c.oid)

            docker_client = docker.from_env()
            runs = executor.run_tests(keep_containers=True)

            for run in runs:
                filters = { "name" : f"act-{run.workflow_name}" }
                containers: List[Container] = docker_client.containers.list(filters=filters)
                if run.failed:
                    logging.error(f"Run failed. Can't export container {c.hex} from {repo_full_name} ({run.workflow}).")
                    for container in containers:
                        container.stop()
                        container.remove()
                    continue

                for container in containers:
                    container.stop()
                    diff_folder_path = os.path.join(export_path, 
                                                repo_full_name.replace('/', '-'), 
                                                c.hex)
                    with diff_file_lock:
                        if not os.path.exists(diff_folder_path):
                            os.makedirs(diff_folder_path)
                        else:
                            # Container already being saved. This may happen if bugs 
                            # were collected from two consecutive commits
                            container.remove()
                            continue
                    diff_file_path = os.path.join(diff_folder_path, container.name)
                    extract_diff(container.id, 
                                diff_file_path, 
                                ignore_paths=['/tmp'])
                    container.remove()

                    workflows = os.path.join(diff_folder_path, 'workflow')
                    os.mkdir(workflows)
                    with open(os.path.join(workflows, f'{run.workflow_name}.yml'), 'w') as f:
                        yaml.dump(run.workflow.doc, f)
                # FIXME: we only consider a single workflow per commit 
                break

            repo_clone.reset(main_commit.oid, pygit2.GIT_RESET_HARD)
            subprocess.run(["git", "clean", "-f", "-d"], cwd=repo_clone.workdir, capture_output=True)
    finally:
        delete_repo_clone(repo_clone)
        if os.path.exists(act_cache_dir):
            shutil.rmtree(act_cache_dir, ignore_errors=True)


def export_bugs(dataset_path, output_folder_path, n_workers=1):
    executor = ThreadPoolExecutor(max_workers=n_workers)
    futures = []

    for jsonl_path in os.listdir(dataset_path):
        with open(os.path.join(dataset_path, jsonl_path), "r") as jsonl:
            lines = jsonl.readlines()
            for line in lines:
                bug = json.loads(line)
                futures.append(executor.submit(export_bug_containers, bug, output_folder_path))

    for future in as_completed(futures):
        future.result()


def main():
    fire.Fire(export_bugs)


if __name__ == '__main__':
    sys.exit(main())
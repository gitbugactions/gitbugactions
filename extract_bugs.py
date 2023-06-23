import os
import uuid
import json
import sys
import pygit2
import docker
import logging
import tempfile
from docker.models.containers import Container
from typing import List
from crawlergpt.test_executor import TestExecutor
from crawlergpt.util import delete_repo_clone
from crawlergpt.docker.export import extract_diff

dataset_path: str = sys.argv[1]
diffs_folder = tempfile.gettempdir()


def export_bug_containers(bug, export_path):
    repo_full_name = bug['repository']
    commit_hash = bug['commit_hash']
    logging.info(f"Exporting {commit_hash} from {repo_full_name}...")
    temp_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
    repo_clone = pygit2.clone_repository(f"https://github.com/{repo_full_name}", temp_path)
    executor = TestExecutor(repo_clone, bug['language'])
    commit: pygit2.Commit = repo_clone.revparse_single(commit_hash)
    previous_commit: pygit2.Commit = repo_clone.revparse_single(commit_hash + "^1")

    for c in [commit, previous_commit]:
        repo_clone.checkout_tree(commit)
        repo_clone.set_head(commit.oid)

        docker_client = docker.from_env()
        runs = executor.run_tests(keep_containers=True)

        for run in runs:
            filters = { "name" : f"act-{run.workflow_name}" }
            containers: List[Container] = docker_client.containers.list(filters=filters)
            for container in containers:
                container.stop()
                diff_file_path = os.path.join(export_path, 
                                              repo_full_name.replace('/', '-'), 
                                              c.hex)
                if not os.path.exists(diff_file_path):
                    os.makedirs(diff_file_path)
                diff_file_path = os.path.join(diff_file_path, container.name)
                extract_diff(container.id, 
                             diff_file_path, 
                             ignore_paths=['/tmp'])
                container.remove()

    delete_repo_clone(repo_clone)


for jsonl_path in os.listdir(dataset_path):
    with open(os.path.join(dataset_path, jsonl_path), "r") as jsonl:
        lines = jsonl.readlines()
        for line in lines:
            bug = json.loads(line)
            export_bug_containers(bug, diffs_folder)

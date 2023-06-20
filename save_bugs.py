import os
import uuid
import json
import sys
import pygit2
import docker
import tempfile
from docker.models.containers import Container
from github import Github
from typing import List
from collect_bugs import PatchCollector
from crawlergpt.util import delete_repo_clone
from crawlergpt.github_token import GithubToken
from crawlergpt.docker.export import extract_last_layer, add_new_layer

dataset_path: str = sys.argv[1]
for jsonl_path in os.listdir(dataset_path):
    with open(os.path.join(dataset_path, jsonl_path), "r") as jsonl:
        lines = jsonl.readlines()
        for line in lines:
            bug = json.loads(line)
            repo = Github(login_or_token=GithubToken.get_token().token).get_repo(bug['repository'])
            collector = PatchCollector(repo)
            repo_clone = pygit2.clone_repository(repo.clone_url,
                                                 os.path.join(tempfile.gettempdir(), str(uuid.uuid4())))
            commit = repo_clone.revparse_single(bug['commit_hash'])
            repo_clone.checkout_tree(commit)
            repo_clone.set_head(commit.oid)

            docker_client = docker.from_env()
            runs = collector.run_tests(repo_clone, keep_containers=True)

            for run in runs:
                filters = {"name":f"act-{run.workflow_name}"}
                containers: List[Container] = docker_client.containers.list(filters=filters)
                for container in containers:
                    # FIXME
                    container.stop()
                    extract_last_layer(container.id, '.')
                    container.remove()

            delete_repo_clone(repo_clone)
            exit(0)

# layer = extract_last_layer('8b74bae099c2', '.')
# add_new_layer("glitch:latest", layer, "glitch:new")
# layer.delete()
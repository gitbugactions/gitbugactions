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
from collect_bugs import PatchCollector, BugPatch
from crawlergpt.util import delete_repo_clone
from crawlergpt.github_token import GithubToken
from crawlergpt.docker.export import extract_diff, apply_diff

dataset_path: str = sys.argv[1]
diffs_folder = tempfile.gettempdir()

def create_act_image(new_image_name, diff_file_path):
    client = docker.from_env()
    container: Container = client.containers.run('crawlergpt:latest', detach=True)
    apply_diff(container.id, diff_file_path)
    repository, tag = new_image_name.split(':')
    container.commit(repository=repository, tag=tag)
    container.stop()
    container.remove()

for jsonl_path in os.listdir(dataset_path):
    with open(os.path.join(dataset_path, jsonl_path), "r") as jsonl:
        lines = jsonl.readlines()
        for line in lines:
            bug = json.loads(line)
            repo = Github(login_or_token=GithubToken.get_token().token).get_repo(bug['repository'])
            # collector = PatchCollector(repo)
            # repo_clone = pygit2.clone_repository(repo.clone_url,
            #                                      os.path.join(tempfile.gettempdir(), str(uuid.uuid4())))
            # commit = repo_clone.revparse_single(bug['commit_hash'])
            # repo_clone.checkout_tree(commit)
            # repo_clone.set_head(commit.oid)

            # docker_client = docker.from_env()
            # runs = collector.run_tests(repo_clone, keep_containers=True)

            # for run in runs:
            #     filters = {"name":f"act-{run.workflow_name}"}
            #     containers: List[Container] = docker_client.containers.list(filters=filters)
            #     for container in containers:
            #         container.stop()
            #         #FIXME
            #         diff_file_path = os.path.join(diffs_folder, str(uuid.uuid4()))
            #         extract_diff(container.id, 
            #                      diff_file_path, 
            #                      ignore_paths=['/tmp'])
            #         container.remove()

            # create_act_image("test:test", diff_file_path)
            repo_clone = pygit2.Repository('/home/nfsaavedra/Downloads/epubcheck/.git')
            
            collector = PatchCollector(repo, runner="test:test", repo_clone=repo_clone)
            bug = BugPatch.from_data(bug)
            print(collector.test_patch(bug))
            print(bug.get_data())
            delete_repo_clone(repo_clone)
            exit(0)

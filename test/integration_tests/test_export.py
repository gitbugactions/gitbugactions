import os
import docker
import uuid
import json
import pygit2
import shutil
import tempfile
import subprocess
import pytest
from crawlergpt.util import delete_repo_clone
from crawlergpt.test_executor import TestExecutor
from crawlergpt.docker.export import create_act_image
from export_bugs import export_bug_containers

repo_clone = None
image_name = None
export_path = None
act_cache_dir = os.path.join(tempfile.gettempdir(), "act-cache", str(uuid.uuid4()))
docker_client = docker.from_env()

@pytest.fixture
def teardown():
    yield
    if image_name is not None:
        docker_client.images.remove(image_name)
    if repo_clone is not None:
        delete_repo_clone(repo_clone)
    if export_path is not None:
        shutil.rmtree(export_path)
    if os.path.exists(act_cache_dir):
        shutil.rmtree(act_cache_dir)

def test_export():
    global repo_clone, image_name, export_path

    with open("test/resources/test_export/alibaba-transmittable-thread-local.json") as f:
        bug = json.loads(f.readlines()[0])
    repo_full_name: str = bug['repository']
    repo_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
    repo_clone = pygit2.clone_repository(f"https://github.com/{repo_full_name}", 
                                         repo_path)
    initial_commit = repo_clone.revparse_single(str(repo_clone.head.target))

    commit_hash = bug['commit_hash']
    commit = repo_clone.revparse_single(commit_hash)
    previous_commit = repo_clone.revparse_single(commit_hash + "^1")
    previous_commit_hash = previous_commit.hex

    export_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
    export_bug_containers(bug, export_path)
    repo_export_path = os.path.join(export_path, repo_full_name.replace('/', '-'))
    assert os.path.exists(repo_export_path)
    assert os.path.exists(os.path.join(repo_export_path, commit_hash))
    assert len(os.listdir(os.path.join(repo_export_path, commit_hash))) == 1
    assert os.path.exists(os.path.join(repo_export_path, previous_commit_hash))
    assert len(os.listdir(os.path.join(repo_export_path, previous_commit_hash))) == 1

    commit_path = os.path.join(repo_export_path, commit_hash)
    commit_container_path = os.path.join(commit_path, os.listdir(commit_path)[0])

    prev_commit_path = os.path.join(repo_export_path, previous_commit_hash)
    prev_commit_container_path = os.path.join(prev_commit_path, os.listdir(prev_commit_path)[0])

    image_name = f"{str(uuid.uuid4())}:latest"
    create_act_image(image_name, commit_container_path)
    executor = TestExecutor(repo_clone, bug['language'], act_cache_dir, runner=image_name)
    repo_clone.checkout_tree(commit)
    repo_clone.set_head(commit.oid)
    runs = executor.run_tests(offline=True)
    assert len(runs) == 1
    assert len(runs[0].failed_tests) == 0
    assert not runs[0].failed

    docker_client.images.remove(image_name)
    repo_clone.reset(initial_commit.oid, pygit2.GIT_RESET_HARD)
    subprocess.run(["git", "clean", "-f", "-d"], cwd=repo_path, capture_output=True)
    repo_clone.checkout_tree(previous_commit)
    repo_clone.set_head(previous_commit.oid)

    image_name = f"{str(uuid.uuid4())}:latest"
    create_act_image(image_name, prev_commit_container_path)

    executor.runner = image_name
    runs = executor.run_tests(offline=True)
    assert len(runs) == 1
    assert len(runs[0].failed_tests) == 0
    assert not runs[0].failed

    repo_clone.reset(previous_commit.oid, pygit2.GIT_RESET_HARD)
    subprocess.run(["git", "clean", "-f", "-d"], cwd=repo_path, capture_output=True)
    repo_clone.apply(pygit2.Diff.parse_diff(bug['test_patch']))
    runs = executor.run_tests(offline=True)
    assert len(runs) == 1
    assert len(runs[0].failed_tests) == 1
    assert not runs[0].failed

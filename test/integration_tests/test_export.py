import os
import uuid
import json
import pygit2
import shutil
import tempfile
import subprocess
import pytest
from gitbugactions.util import delete_repo_clone
from gitbugactions.docker.client import DockerClient
from export_bugs import export_bug_containers
from run_bug import run_bug

repo_clone = None
export_path = None
act_cache_dir = os.path.join(tempfile.gettempdir(), "act-cache", str(uuid.uuid4()))
docker_client = DockerClient.getInstance()


def teardown_module():
    if repo_clone is not None:
        delete_repo_clone(repo_clone)
    if export_path is not None:
        shutil.rmtree(export_path)
    if os.path.exists(act_cache_dir):
        shutil.rmtree(act_cache_dir)


@pytest.mark.dependency()
def test_export_bug_containers():
    global repo_clone, export_path

    with open("test/resources/test_export/tidwall-expr.json") as f:
        bug = json.loads(f.readlines()[0])
    repo_full_name: str = bug["repository"]
    repo_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
    repo_clone = pygit2.clone_repository(
        f"https://github.com/{repo_full_name}", repo_path
    )

    commit_hash = bug["commit_hash"]
    export_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
    export_bug_containers(bug, export_path)
    repo_export_path = os.path.join(export_path, repo_full_name.replace("/", "-"))
    assert os.path.exists(repo_export_path)
    assert os.path.exists(os.path.join(repo_export_path, commit_hash))
    assert len(os.listdir(os.path.join(repo_export_path, commit_hash))) == 2


@pytest.mark.dependency(depends=["test_export_bug_containers"])
def test_run_bug():
    with open("test/resources/test_export/tidwall-expr.json") as f:
        bug = json.loads(f.readlines()[0])
    repo_path = repo_clone.workdir
    repo_full_name: str = bug["repository"]
    commit_hash = bug["commit_hash"]
    previous_commit = repo_clone.revparse_single(commit_hash + "^1")
    commit = repo_clone.revparse_single(commit_hash)
    initial_commit = repo_clone.revparse_single(str(repo_clone.head.target))

    repo_clone.checkout_tree(commit)
    repo_clone.set_head(commit.id)

    runs = run_bug(
        repo_full_name,
        commit_hash,
        repo_path,
        "test/resources/test_export",
        export_path,
        offline=True,
    )
    assert len(runs) == 1
    assert len(runs[0].failed_tests) == 0
    assert not runs[0].failed

    repo_clone.reset(initial_commit.id, pygit2.GIT_RESET_HARD)
    subprocess.run(
        ["git", "clean", "-f", "-d", "-x"], cwd=repo_path, capture_output=True
    )
    repo_clone.checkout_tree(previous_commit)
    repo_clone.set_head(previous_commit.id)
    repo_clone.apply(pygit2.Diff.parse_diff(bug["non_code_patch"]))

    runs = run_bug(
        repo_full_name,
        commit_hash,
        repo_path,
        "test/resources/test_export",
        export_path,
        offline=True,
    )
    assert len(runs) == 1
    assert len(runs[0].failed_tests) == 0
    assert not runs[0].failed

    repo_clone.reset(initial_commit.id, pygit2.GIT_RESET_HARD)
    subprocess.run(
        ["git", "clean", "-f", "-d", "-x"], cwd=repo_path, capture_output=True
    )
    repo_clone.checkout_tree(previous_commit)
    repo_clone.set_head(previous_commit.id)
    repo_clone.apply(pygit2.Diff.parse_diff(bug["non_code_patch"]))
    repo_clone.apply(pygit2.Diff.parse_diff(bug["test_patch"]))

    runs = run_bug(
        repo_full_name,
        commit_hash,
        repo_path,
        "test/resources/test_export",
        export_path,
        offline=True,
    )
    assert len(runs) == 1
    assert len(runs[0].failed_tests) == 1
    assert not runs[0].failed

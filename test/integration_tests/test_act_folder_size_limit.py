import os
import pytest
from uuid import uuid4
from tempfile import gettempdir
from crawlergpt.actions.actions import Act, ActCacheDirManager
from crawlergpt.actions.workflow import GitHubWorkflowFactory
from crawlergpt.util import clone_repo, delete_repo_clone

act_cache_dir = ActCacheDirManager.acquire_act_cache_dir()
path = os.path.join(gettempdir(), str(uuid4()))
repo = clone_repo("https://github.com/andre15silva/crawlergpt-pytest-test-repo", path)


@pytest.fixture
def teardown():
    yield
    delete_repo_clone(repo)
    ActCacheDirManager.return_act_cache_dir(act_cache_dir)


def test_act_folder_size_limit(teardown):
    workflow = GitHubWorkflowFactory().create_workflow(
        os.path.join(repo.workdir, ".github", "workflows", "tests.yml"), "python"
    )
    act = Act(False, folder_size_limit=10000)
    run = act.run_act(repo.workdir, workflow, act_cache_dir)
    assert run.failed

import pytest
from collect_bugs import PatchCollector
from crawlergpt.github_token import GithubToken
from crawlergpt.actions.actions import Act

@pytest.fixture
def setup():
    global collector
    collector = PatchCollector(
        GithubToken.get_token().github.get_repo("Nfsaavedra/crawlergpt-test-repo")
    )
    yield


@pytest.fixture
def teardown():
    yield
    collector.delete_repo()
    Act.set_memory_limit("7g")


def test_memory_limit(setup, teardown):
    patches = collector.get_possible_patches()

    for patch in patches:
        collector.test_patch(patch)
        assert patch.actions_runs != [None, None, None]

    # 6m is the minimum limit
    Act.set_memory_limit("6m")

    for patch in patches:
        collector.test_patch(patch)
        assert patch.actions_runs == [None, None, None]

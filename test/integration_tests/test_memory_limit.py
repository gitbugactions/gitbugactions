import pytest
from collect_bugs import PatchCollector
from gitbugactions.github_api import GithubAPI
from gitbugactions.actions.actions import Act


@pytest.fixture
def setup():
    global collector
    collector = PatchCollector(
        GithubAPI().get_repo("gitbugactions/gitbugactions-maven-test-repo")
    )
    collector.set_default_github_actions()
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

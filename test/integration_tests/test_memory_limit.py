import pytest
from collect_bugs import PatchCollector
from crawlergpt.github_token import GithubToken
from crawlergpt.actions.actions import Act

collector = PatchCollector(
    GithubToken.get_token().github.get_repo("Nfsaavedra/crawlergpt-test-repo")
)


@pytest.fixture
def teardown():
    yield
    collector.delete_repo()


def test_memory_limit(teardown):
    patches = collector.get_possible_patches()

    for patch in patches:
        collector.test_patch(patch)
        assert patch.actions_runs != [None, None, None]

    # 6m is the minimum limit
    Act.set_memory_limit("6m")

    for patch in patches:
        collector.test_patch(patch)
        assert patch.actions_runs == [None, None, None]

import json
import shutil
import pytest
from collect_bugs import collect_bugs

@pytest.fixture
def teardown_out_bugs():
    yield
    shutil.rmtree("test/resources/test_collect_bugs_out")

def test_collect_bugs(teardown_out_bugs):
    collect_bugs("test/resources/test_collect_bugs", "test/resources/test_collect_bugs_out", 2)
    with open("test/resources/test_collect_bugs_out/Nfsaavedra-crawlergpt-test-repo.json", "r") as f:
        lines = f.readlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["commit_hash"] == "ef34d133079591972a5ce9442cbcc7603003d938"
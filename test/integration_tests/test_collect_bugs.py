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
        assert len(data["actions_runs"]) == 3
        assert len(data["actions_runs"][1][0]["tests"]) == 1
        assert len(data["actions_runs"][1][0]["tests"][0]["results"]) == 1
        assert data["actions_runs"][1][0]["tests"][0]["results"][0]['result'] == 'Failure'
        assert data["commit_timestamp"] == "2023-06-05T13:19:21Z"
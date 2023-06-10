import json
import shutil
import pytest
from collect_bugs import collect_bugs

@pytest.fixture
def teardown_out_bugs():
    yield
    shutil.rmtree("test/resources/test_collect_bugs_out")

def get_test_results(tests):
    passed, failure = 0, 0

    for test in tests:
        if test["results"][0]['result'] == 'Passed':
            passed += 1
        elif test["results"][0]['result'] == 'Failure':
            failure += 1

    return passed, failure

def test_collect_bugs(teardown_out_bugs):
    collect_bugs("test/resources/test_collect_bugs", "test/resources/test_collect_bugs_out", 2)
    with open("test/resources/test_collect_bugs_out/Nfsaavedra-crawlergpt-test-repo.json", "r") as f:
        lines = f.readlines()
        assert len(lines) == 2
        data = json.loads(lines[0])
        assert data["commit_hash"] == "248d0b1f31e0c9b82eda0e9a9c15cb6bbeaec0b0"
        assert data["strategy"] == "FAIL_PASS"
        assert len(data["actions_runs"]) == 3
        assert len(data["actions_runs"][0][0]["tests"]) == 2
        assert data["actions_runs"][1] is None
        assert len(data["actions_runs"][2][0]["tests"]) == 2
        assert data["commit_timestamp"] == "2023-06-10T15:23:09Z"
        passed, failure = get_test_results(data["actions_runs"][0][0]["tests"])
        assert passed == 1
        assert failure == 1

        data = json.loads(lines[1])
        assert data["commit_hash"] == "ef34d133079591972a5ce9442cbcc7603003d938"
        assert data["strategy"] == "PASS_PASS"
        assert len(data["actions_runs"]) == 3
        assert len(data["actions_runs"][1][0]["tests"]) == 1
        assert len(data["actions_runs"][1][0]["tests"][0]["results"]) == 1
        assert data["actions_runs"][1][0]["tests"][0]["results"][0]['result'] == 'Failure'
        assert data["commit_timestamp"] == "2023-06-05T13:19:21Z"
        
    with open("test/resources/test_collect_bugs_out/andre15silva-crawlergpt-pytest-test-repo.json", "r") as f:
        lines = f.readlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["commit_hash"] == "0e1907f75fcd3936b6d64292bc278250f2ee9ca3"
        assert data["strategy"] == "PASS_PASS"
        assert len(data["actions_runs"]) == 3
        # assert that number of total tests before == 6 and all pass
        assert len(data["actions_runs"][0][0]["tests"]) == 6
        assert all([x["result"] == "Passed" for x in [r for _ in [y["results"] for y in data["actions_runs"][0][0]["tests"]] for r in _]])
        # assert that number of tests failing before w/ new tests == 12, 6 pass and 6 fail
        assert len(data["actions_runs"][1][0]["tests"]) == 12
        assert len([x for x in [r for _ in [y["results"] for y in data["actions_runs"][1][0]["tests"]] for r in _] if x["result"] == "Passed"])
        assert len([x for x in [r for _ in [y["results"] for y in data["actions_runs"][1][0]["tests"]] for r in _] if x["result"] == "Failure"])
        # assert that number of total tests after == 12 and all pass
        assert len(data["actions_runs"][2][0]["tests"]) == 12
        assert all([x["result"] == "Passed" for x in [r for _ in [y["results"] for y in data["actions_runs"][2][0]["tests"]] for r in _]])
        assert data["commit_timestamp"] == "2023-06-09T20:06:31Z"

import json
import shutil
import pytest
from collect_bugs import collect_bugs, PatchCollector
from crawlergpt.github_token import GithubToken


def get_token_usage():
    token_usage = 0
    if GithubToken.has_tokens():
        for token in GithubToken._GithubToken__TOKENS:
            token_usage += 5000 - token.remaining
        return token_usage
    return token_usage


def get_test_results(tests):
    passed, failure = 0, 0
    for test in tests:
        if test["results"][0]['result'] == 'Passed':
            passed += 1
        elif test["results"][0]['result'] == 'Failure':
            failure += 1
    return passed, failure


def test_get_related_commit_info():
    collector = PatchCollector(GithubToken.get_token().github.get_repo('ASSERT-KTH/flacoco'))
    issues = collector._PatchCollector__get_related_commit_info("7bc38df")
    assert len(issues) == 1
    assert issues[0]['id'] == 100
    assert issues[0]['title'] == 'Include java 1 to 4 instruction sets in CI'
    assert issues[0]['body'] == "This PR fixes the gap in CI, where the 4 first major versions of the Java instruction set weren't covered.\r\n\r\nJacoco supports 1 to 16 right now, so we can also claim that we do so."
    assert len(issues[0]['comments']) == 0
    assert len(issues[0]['labels']) == 0
    assert issues[0]['is_pull_request'] == True
    assert len(issues[0]['review_comments']) == 2
    shutil.rmtree(collector.repo_path)

    collector = PatchCollector(GithubToken.get_token().github.get_repo('sr-lab/GLITCH'))
    issues = collector._PatchCollector__get_related_commit_info("98dd01d")
    assert len(issues) == 1
    assert issues[0]['id'] == 15
    assert issues[0]['title'] == 'Fix vscode extension for Ansible'
    assert issues[0]['body'] == 'Since autodetect was removed, the extension has to be updated.'
    assert issues[0]['is_pull_request'] == False
    shutil.rmtree(collector.repo_path)


class TestCollectBugs():
    
    TOKEN_USAGE: int = 0

    @classmethod
    def setup_class(cls):
        GithubToken.init_tokens()
        TestCollectBugs.TOKEN_USAGE = get_token_usage()
        collect_bugs("test/resources/test_collect_bugs", "test/resources/test_collect_bugs_out", 16)

    @classmethod
    def teardown_class(cls):
        shutil.rmtree("test/resources/test_collect_bugs_out")


    def test_crawlergpt_test_repo(self):
        """
        Verifies that the maven project bugs have been found
        
        repo: https://github.com/Nfsaavedra/crawlergpt-test-repo
        """
        with open("test/resources/test_collect_bugs_out/Nfsaavedra-crawlergpt-test-repo.json", "r") as f:
            lines = f.readlines()
            assert len(lines) == 2
            data = json.loads(lines[0])
            assert data["commit_hash"] == "7e11161b4983f8ff9fd056fa465c8cabaa8a7f80"
            assert data["strategy"] == "FAIL_PASS"
            assert len(data["actions_runs"]) == 3
            assert len(data["actions_runs"][0][0]["tests"]) == 2
            assert data["actions_runs"][1] is None
            assert len(data["actions_runs"][2][0]["tests"]) == 2
            assert len(data["issues"]) == 1
            assert data["issues"][0]["title"] == "Subtract is not working"
            assert data["issues"][0]["body"] == "Test"
            assert len(data["issues"][0]["comments"]) == 1
            assert data["issues"][0]["comments"][0] == "Test"
            assert data["commit_timestamp"] == "2023-06-16T14:16:27Z"
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


    def test_crawlergpt_pytest_test_repo(self):
        """
        Verifies that the pytest project bugs have been found
        
        repo: https://github.com/andre15silva/crawlergpt-pytest-test-repo
        """
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
            assert len([x for x in [r for _ in [y["results"] for y in data["actions_runs"][1][0]["tests"]] for r in _] if x["result"] == "Passed"]) == 6
            assert len([x for x in [r for _ in [y["results"] for y in data["actions_runs"][1][0]["tests"]] for r in _] if x["result"] == "Failure"]) == 6
            # assert that number of total tests after == 12 and all pass
            assert len(data["actions_runs"][2][0]["tests"]) == 12
            assert all([x["result"] == "Passed" for x in [r for _ in [y["results"] for y in data["actions_runs"][2][0]["tests"]] for r in _]])
            assert data["commit_timestamp"] == "2023-06-09T20:06:31Z"


    def test_crawlergpt_gradle_test_repo(self):
        """
        Verifies that the gradle project bugs have been found
        
        repo: https://github.com/andre15silva/crawlergpt-gradle-test-repo
        """
        with open("test/resources/test_collect_bugs_out/andre15silva-crawlergpt-gradle-test-repo.json", "r") as f:
            lines = f.readlines()
            assert len(lines) == 1
            data = json.loads(lines[0])
            assert data["commit_hash"] == "2289b33a322f01b95405905c53770a63fa21b8bf"
            assert len(data["actions_runs"]) == 3
            # assert that number of total tests before == 1 and it passes
            assert len(data["actions_runs"][0][0]["tests"]) == 1
            assert all([x["result"] == "Passed" for x in [r for _ in [y["results"] for y in data["actions_runs"][0][0]["tests"]] for r in _]])
            # assert that number of tests failing before w/ new tests == 1 and it fails
            assert len(data["actions_runs"][1][0]["tests"]) == 1
            assert len([x for x in [r for _ in [y["results"] for y in data["actions_runs"][1][0]["tests"]] for r in _] if x["result"] == "Passed"]) == 0
            assert len([x for x in [r for _ in [y["results"] for y in data["actions_runs"][1][0]["tests"]] for r in _] if x["result"] == "Failure"]) == 1
            # assert that number of total tests after == 1 and it passes
            assert len(data["actions_runs"][2][0]["tests"]) == 1
            assert all([x["result"] == "Passed" for x in [r for _ in [y["results"] for y in data["actions_runs"][2][0]["tests"]] for r in _]])
            assert data["commit_timestamp"] == "2023-06-10T15:07:36Z"


    def test_crawlergpt_unittest_test_repo(self):
        """
        Verifies that the unittest project bugs have been found
        
        repo: https://github.com/andre15silva/crawlergpt-unittest-test-repo
        """
        with open("test/resources/test_collect_bugs_out/andre15silva-crawlergpt-unittest-test-repo.json", "r") as f:
            lines = f.readlines()
            assert len(lines) == 1
            data = json.loads(lines[0])
            assert data["commit_hash"] == "d3d7a607e3a8abc330f8fd69f677284a9afaf650"
            assert data["strategy"] == "PASS_PASS"
            assert len(data["actions_runs"]) == 3
            # assert that number of total tests before == 2 and all pass
            assert len(data["actions_runs"][0][0]["tests"]) == 2
            assert all([x["result"] == "Passed" for x in [r for _ in [y["results"] for y in data["actions_runs"][0][0]["tests"]] for r in _]])
            # assert that number of tests failing before w/ new tests == 3, 2 pass and 1 fail
            assert len(data["actions_runs"][1][0]["tests"]) == 3
            assert len([x for x in [r for _ in [y["results"] for y in data["actions_runs"][1][0]["tests"]] for r in _] if x["result"] == "Passed"]) == 2
            assert len([x for x in [r for _ in [y["results"] for y in data["actions_runs"][1][0]["tests"]] for r in _] if x["result"] == "Failure"]) == 1
            # assert that number of total tests after == 3 and all pass
            assert len(data["actions_runs"][2][0]["tests"]) == 3
            assert all([x["result"] == "Passed" for x in [r for _ in [y["results"] for y in data["actions_runs"][2][0]["tests"]] for r in _]])
            assert data["commit_timestamp"] == "2023-06-20T14:54:30Z"
            
    
    @pytest.mark.depends(on=[
        'test_crawlergpt_test_repo',
        'test_crawlergpt_pytest_test_repo',
        'test_crawlergpt_gradle_test_repo',
        'test_crawlergpt_unittest_test_repo',
        ])
    @pytest.mark.flaky
    @pytest.mark.skip(reason="flaky due to non-determinism in token usage during this class")
    def test_token_usage(self):
        # FIXME: flaky
        if GithubToken.has_tokens():
            assert TestCollectBugs.TOKEN_USAGE + 8 == get_token_usage()

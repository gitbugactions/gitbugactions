import json
import shutil
import pytest
from typing import List
from unidiff import PatchSet
from collect_bugs import collect_bugs, PatchCollector, BugPatch
from crawlergpt.github_token import GithubToken
from crawlergpt.util import delete_repo_clone
from crawlergpt.actions.actions import ActCacheDirManager


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
        if test["results"][0]["result"] == "Passed":
            passed += 1
        elif test["results"][0]["result"] == "Failure":
            failure += 1
    return passed, failure


def test_get_related_commit_info():
    collector = PatchCollector(
        GithubToken.get_token().github.get_repo("ASSERT-KTH/flacoco")
    )
    issues = collector._PatchCollector__get_related_commit_info("7bc38df")
    assert len(issues) == 1
    assert issues[0]["id"] == 100
    assert issues[0]["title"] == "Include java 1 to 4 instruction sets in CI"
    assert (
        issues[0]["body"]
        == "This PR fixes the gap in CI, where the 4 first major versions of the Java instruction set weren't covered.\r\n\r\nJacoco supports 1 to 16 right now, so we can also claim that we do so."
    )
    assert len(issues[0]["comments"]) == 0
    assert len(issues[0]["labels"]) == 0
    assert issues[0]["is_pull_request"] == True
    assert len(issues[0]["review_comments"]) == 2
    shutil.rmtree(collector.repo_clone.workdir)

    collector = PatchCollector(GithubToken.get_token().github.get_repo("sr-lab/GLITCH"))
    issues = collector._PatchCollector__get_related_commit_info("98dd01d")
    assert len(issues) == 1
    assert issues[0]["id"] == 15
    assert issues[0]["title"] == "Fix vscode extension for Ansible"
    assert (
        issues[0]["body"]
        == "Since autodetect was removed, the extension has to be updated."
    )
    assert issues[0]["is_pull_request"] == False
    delete_repo_clone(collector.repo_clone)


def test_get_possible_patches():
    collector = PatchCollector(
        GithubToken.get_token().github.get_repo("HubSpot/jinjava")
    )
    patches: List[BugPatch] = collector.get_possible_patches()
    commits = list(map(lambda patch: patch.commit, patches))

    # The diffs are equal, at least one of the commits should be in the list, but not both
    assert ("c5a7737cea8d078efbb3d8d3c78c6ec7e32d1861" in commits) ^ (
        "04fdd485697ed82232b5097d22ddb46ff234bb3b" in commits
    )
    assert ("b12cc483dc6f2205c901d5caeb91e0658b913c6b" in commits) ^ (
        "c15bfc7cc066b85585831a8770a6d00daf8272aa" in commits
    )

    # 8a316 is a merge commit and 38eeb is a fix before the merge
    assert "38eeb1f660cd6b28dcce925d64dc9112c31745d6" in commits
    assert "8a316e3e7043f7663256b039d73696a5363cbcb8" not in commits

    # Two commits with different fixes which point to the same previous commit
    assert "23e97170add0cb770dea4f70c93c19de394525c9" in commits
    assert "c58e65e0ab421fba2987e2efec18f49e87a294a6" in commits
    # Merge commit equal to 23e97 but with different previous commit
    # The patch is discarded because it is oldest than 23e97
    assert "0d8347de05e969cb2fc836bb0f5e343643b2e7ad" not in commits

    delete_repo_clone(collector.repo_clone)


@pytest.mark.skip(
    reason="""this test doesn't add much, but it is a good sanity test. 
              skipping to avoid overloading the tests"""
)
def test_get_possible_patches():
    try:
        collector = PatchCollector(
            GithubToken.get_token().github.get_repo("Nfsaavedra/crawlergpt-test-repo")
        )
        bug_patch = collector.get_possible_patches()[0]
        act_cache_dir = ActCacheDirManager.acquire_act_cache_dir()
        runs = collector._PatchCollector__test_patch(
            bug_patch.commit,
            bug_patch.previous_commit,
            bug_patch.test_patch,
            act_cache_dir,
        )
        assert collector._PatchCollector__check_tests_were_fixed(runs[1], runs[2])
        assert not collector._PatchCollector__check_tests_were_fixed(runs[1], runs[1])
    finally:
        collector.delete_repo()


class TestCollectBugs:
    TOKEN_USAGE: int = 0

    @classmethod
    def setup_class(cls):
        GithubToken.init_tokens()
        TestCollectBugs.TOKEN_USAGE = get_token_usage()
        collect_bugs(
            "test/resources/test_collect_bugs",
            "test/resources/test_collect_bugs_out",
            16,
        )

    @classmethod
    def teardown_class(cls):
        shutil.rmtree("test/resources/test_collect_bugs_out")

    @pytest.mark.dependency()
    def test_crawlergpt_test_repo(self):
        """
        Verifies that the maven project bugs have been found

        repo: https://github.com/Nfsaavedra/crawlergpt-test-repo
        """
        with open(
            "test/resources/test_collect_bugs_out/Nfsaavedra-crawlergpt-test-repo.json",
            "r",
        ) as f:
            lines = f.readlines()
            assert len(lines) == 2

            for line in lines:
                data = json.loads(line)
                assert data["commit_hash"] in [
                    "ef34d133079591972a5ce9442cbcc7603003d938",
                    "7e11161b4983f8ff9fd056fa465c8cabaa8a7f80",
                ]

                if data["commit_hash"] == "ef34d133079591972a5ce9442cbcc7603003d938":
                    assert data["commit_message"] == "Fix sum\n"
                    assert data["commit_timestamp"] == "2023-06-05T13:19:21Z"
                    assert (
                        data["previous_commit_hash"]
                        == "cad6744850817b708400736678d2601cbd1c1dd6"
                    )
                    assert data["previous_commit_message"] == "Add gitignore\n"
                    assert data["previous_commit_timestamp"] == "2023-06-05T13:19:12Z"
                    assert data["time_to_patch"] == "0:00:09"
                    assert data["strategy"] == "PASS_PASS"
                    assert data["bug_patch_files_type"] == "SOURCE_ONLY"
                    assert len(data["actions_runs"]) == 3
                    assert len(data["actions_runs"][1][0]["tests"]) == 1
                    assert len(data["actions_runs"][1][0]["tests"][0]["results"]) == 1
                    assert (
                        data["actions_runs"][1][0]["tests"][0]["results"][0]["result"]
                        == "Failure"
                    )
                    assert data["commit_timestamp"] == "2023-06-05T13:19:21Z"

                elif data["commit_hash"] == "7e11161b4983f8ff9fd056fa465c8cabaa8a7f80":
                    assert data["commit_message"] == "Fix subtract. Fixes #1\n"
                    assert data["commit_timestamp"] == "2023-06-16T14:16:27Z"
                    assert (
                        data["previous_commit_hash"]
                        == "5871e6f8f072b4b3e07d4753c55c6c6302419b1e"
                    )
                    assert data["previous_commit_message"] == "Add subtract feature\n"
                    assert data["previous_commit_timestamp"] == "2023-06-10T15:22:49Z"
                    assert data["time_to_patch"] == "5 days, 22:53:38"
                    assert data["strategy"] == "FAIL_PASS"
                    assert data["bug_patch_files_type"] == "SOURCE_ONLY"
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
                    passed, failure = get_test_results(
                        data["actions_runs"][0][0]["tests"]
                    )
                    assert passed == 1
                    assert failure == 1

    @pytest.mark.dependency()
    def test_crawlergpt_pytest_test_repo(self):
        """
        Verifies that the pytest project bugs have been found

        repo: https://github.com/andre15silva/crawlergpt-pytest-test-repo
        """
        with open(
            "test/resources/test_collect_bugs_out/andre15silva-crawlergpt-pytest-test-repo.json",
            "r",
        ) as f:
            lines = f.readlines()
            assert len(lines) == 3

            for line in lines:
                data = json.loads(line)
                assert data["commit_hash"] in [
                    "0e1907f75fcd3936b6d64292bc278250f2ee9ca3",
                    "fc7ce580d4ea1a8af029b31f14aba881a4c02368",
                    "05e841e86b09a60324dd77aa6d247bfa6331ad9e",
                ]

                if data["commit_hash"] == "0e1907f75fcd3936b6d64292bc278250f2ee9ca3":
                    assert data["commit_message"] == "fix sum\n"
                    assert data["commit_timestamp"] == "2023-06-09T20:06:31Z"
                    assert (
                        data["previous_commit_hash"]
                        == "fd90a022e97988819f93abdc8828dd75e5f50776"
                    )
                    assert data["previous_commit_message"] == "initial implementation\n"
                    assert data["previous_commit_timestamp"] == "2023-06-09T20:05:56Z"
                    assert data["time_to_patch"] == "0:00:35"
                    assert data["strategy"] == "PASS_PASS"
                    assert data["bug_patch_files_type"] == "SOURCE_ONLY"
                    assert len(data["actions_runs"]) == 3
                    # assert that number of total tests before == 6 and all pass
                    assert len(data["actions_runs"][0][0]["tests"]) == 6
                    assert all(
                        [
                            x["result"] == "Passed"
                            for x in [
                                r
                                for _ in [
                                    y["results"]
                                    for y in data["actions_runs"][0][0]["tests"]
                                ]
                                for r in _
                            ]
                        ]
                    )
                    # assert that number of tests failing before w/ new tests == 12, 6 pass and 6 fail
                    assert len(data["actions_runs"][1][0]["tests"]) == 12
                    assert (
                        len(
                            [
                                x
                                for x in [
                                    r
                                    for _ in [
                                        y["results"]
                                        for y in data["actions_runs"][1][0]["tests"]
                                    ]
                                    for r in _
                                ]
                                if x["result"] == "Passed"
                            ]
                        )
                        == 6
                    )
                    assert (
                        len(
                            [
                                x
                                for x in [
                                    r
                                    for _ in [
                                        y["results"]
                                        for y in data["actions_runs"][1][0]["tests"]
                                    ]
                                    for r in _
                                ]
                                if x["result"] == "Failure"
                            ]
                        )
                        == 6
                    )
                    # assert that number of total tests after == 12 and all pass
                    assert len(data["actions_runs"][2][0]["tests"]) == 12
                    assert all(
                        [
                            x["result"] == "Passed"
                            for x in [
                                r
                                for _ in [
                                    y["results"]
                                    for y in data["actions_runs"][2][0]["tests"]
                                ]
                                for r in _
                            ]
                        ]
                    )

                elif data["commit_hash"] == "fc7ce580d4ea1a8af029b31f14aba881a4c02368":
                    assert data["commit_message"] == "fix pi\n"
                    assert data["commit_timestamp"] == "2023-07-03T09:33:35Z"
                    assert (
                        data["previous_commit_hash"]
                        == "3b1fba52bb74343dfd2466446cbfd94f1f1700f9"
                    )
                    assert data["previous_commit_message"] == "implement pi\n"
                    assert data["previous_commit_timestamp"] == "2023-07-03T09:32:44Z"
                    assert data["time_to_patch"] == "0:00:51"
                    assert data["strategy"] == "FAIL_PASS"
                    assert data["bug_patch_files_type"] == "NON_SOURCE_ONLY"
                    assert len(data["actions_runs"]) == 3
                    assert len(data["actions_runs"][0][0]["tests"]) == 13
                    assert len(data["actions_runs"][2][0]["tests"]) == 13

                elif data["commit_hash"] == "05e841e86b09a60324dd77aa6d247bfa6331ad9e":
                    assert data["commit_message"] == "fix golden\n"
                    assert data["commit_timestamp"] == "2023-07-03T09:39:47Z"
                    assert (
                        data["previous_commit_hash"]
                        == "cb83f8851cc1a4f30bef7e096c22caba10cb450f"
                    )
                    assert data["previous_commit_message"] == "implement golden\n"
                    assert data["previous_commit_timestamp"] == "2023-07-03T09:39:24Z"
                    assert data["time_to_patch"] == "0:00:23"
                    assert data["strategy"] == "FAIL_PASS"
                    assert data["bug_patch_files_type"] == "MIXED"
                    assert len(data["actions_runs"]) == 3
                    assert len(data["actions_runs"][0][0]["tests"]) == 15
                    assert len(data["actions_runs"][2][0]["tests"]) == 15

    @pytest.mark.dependency()
    def test_crawlergpt_gradle_test_repo(self):
        """
        Verifies that the gradle project bugs have been found

        repo: https://github.com/andre15silva/crawlergpt-gradle-test-repo
        """
        with open(
            "test/resources/test_collect_bugs_out/andre15silva-crawlergpt-gradle-test-repo.json",
            "r",
        ) as f:
            lines = f.readlines()
            assert len(lines) == 1
            data = json.loads(lines[0])
            assert data["commit_hash"] == "2289b33a322f01b95405905c53770a63fa21b8bf"
            assert data["commit_message"] == "fix sum\n"
            assert data["commit_timestamp"] == "2023-06-10T15:07:36Z"
            assert (
                data["previous_commit_hash"]
                == "cab2445ecf7788bed39802d716ae095fc499cafa"
            )
            assert data["previous_commit_message"] == "initial implementation\n"
            assert data["previous_commit_timestamp"] == "2023-06-10T15:07:10Z"
            assert data["time_to_patch"] == "0:00:26"
            assert data["strategy"] == "PASS_PASS"
            assert data["bug_patch_files_type"] == "SOURCE_ONLY"
            assert len(data["actions_runs"]) == 3
            # assert that number of total tests before == 1 and it passes
            assert len(data["actions_runs"][0][0]["tests"]) == 1
            assert all(
                [
                    x["result"] == "Passed"
                    for x in [
                        r
                        for _ in [
                            y["results"] for y in data["actions_runs"][0][0]["tests"]
                        ]
                        for r in _
                    ]
                ]
            )
            # assert that number of tests failing before w/ new tests == 1 and it fails
            assert len(data["actions_runs"][1][0]["tests"]) == 1
            assert (
                len(
                    [
                        x
                        for x in [
                            r
                            for _ in [
                                y["results"]
                                for y in data["actions_runs"][1][0]["tests"]
                            ]
                            for r in _
                        ]
                        if x["result"] == "Passed"
                    ]
                )
                == 0
            )
            assert (
                len(
                    [
                        x
                        for x in [
                            r
                            for _ in [
                                y["results"]
                                for y in data["actions_runs"][1][0]["tests"]
                            ]
                            for r in _
                        ]
                        if x["result"] == "Failure"
                    ]
                )
                == 1
            )
            # assert that number of total tests after == 1 and it passes
            assert len(data["actions_runs"][2][0]["tests"]) == 1
            assert all(
                [
                    x["result"] == "Passed"
                    for x in [
                        r
                        for _ in [
                            y["results"] for y in data["actions_runs"][2][0]["tests"]
                        ]
                        for r in _
                    ]
                ]
            )

    @pytest.mark.dependency()
    def test_crawlergpt_unittest_test_repo(self):
        """
        Verifies that the unittest project bugs have been found

        repo: https://github.com/andre15silva/crawlergpt-unittest-test-repo
        """
        with open(
            "test/resources/test_collect_bugs_out/andre15silva-crawlergpt-unittest-test-repo.json",
            "r",
        ) as f:
            lines = f.readlines()
            assert len(lines) == 1
            data = json.loads(lines[0])
            assert data["commit_hash"] == "d3d7a607e3a8abc330f8fd69f677284a9afaf650"
            assert data["commit_timestamp"] == "2023-06-20T14:54:30Z"
            assert data["commit_message"] == "fix sum\n"
            assert (
                data["previous_commit_hash"]
                == "73a8a00fc8bbbe0af1351b4e97682138a32981b2"
            )
            assert data["previous_commit_message"] == "initial implementation\n"
            assert data["previous_commit_timestamp"] == "2023-06-20T14:54:25Z"
            assert data["time_to_patch"] == "0:00:05"
            assert data["strategy"] == "PASS_PASS"
            assert data["bug_patch_files_type"] == "SOURCE_ONLY"
            assert len(data["actions_runs"]) == 3
            # assert that number of total tests before == 2 and all pass
            assert len(data["actions_runs"][0][0]["tests"]) == 2
            assert all(
                [
                    x["result"] == "Passed"
                    for x in [
                        r
                        for _ in [
                            y["results"] for y in data["actions_runs"][0][0]["tests"]
                        ]
                        for r in _
                    ]
                ]
            )
            # assert that number of tests failing before w/ new tests == 3, 2 pass and 1 fail
            assert len(data["actions_runs"][1][0]["tests"]) == 3
            assert (
                len(
                    [
                        x
                        for x in [
                            r
                            for _ in [
                                y["results"]
                                for y in data["actions_runs"][1][0]["tests"]
                            ]
                            for r in _
                        ]
                        if x["result"] == "Passed"
                    ]
                )
                == 2
            )
            assert (
                len(
                    [
                        x
                        for x in [
                            r
                            for _ in [
                                y["results"]
                                for y in data["actions_runs"][1][0]["tests"]
                            ]
                            for r in _
                        ]
                        if x["result"] == "Failure"
                    ]
                )
                == 1
            )
            # assert that number of total tests after == 3 and all pass
            assert len(data["actions_runs"][2][0]["tests"]) == 3
            assert all(
                [
                    x["result"] == "Passed"
                    for x in [
                        r
                        for _ in [
                            y["results"] for y in data["actions_runs"][2][0]["tests"]
                        ]
                        for r in _
                    ]
                ]
            )

    @pytest.mark.dependency(
        depends=[
            "TestCollectBugs::test_crawlergpt_test_repo",
            "TestCollectBugs::test_crawlergpt_pytest_test_repo",
            "TestCollectBugs::test_crawlergpt_gradle_test_repo",
            "TestCollectBugs::test_crawlergpt_unittest_test_repo",
        ]
    )
    @pytest.mark.flaky
    @pytest.mark.skip(
        reason="flaky due to non-determinism in token usage during this class"
    )
    def test_token_usage(self):
        # FIXME: flaky
        if GithubToken.has_tokens():
            assert TestCollectBugs.TOKEN_USAGE + 8 == get_token_usage()

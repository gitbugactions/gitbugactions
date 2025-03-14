import os
import json
import shutil
from collect_bugs import collect_bugs
from test.integration_tests.test_collect_bugs import TestCollectBugs


class TestCollectBugsPython(TestCollectBugs):
    LANGUAGE = "python"

    @classmethod
    def setup_class(cls):
        super().setup_class()
        collect_bugs(
            "test/resources/test_collect_bugs_python",
            "test/resources/test_collect_bugs_python_out",
            4,
            strategies=["PASS_PASS", "FAIL_PASS", "FAIL_FAIL", "FAIL_PASS_BUILD"],
            filter_on_commit_time_start="2020-01-01 00:00 UTC",
            pull_requests=True,
        )

    @classmethod
    def teardown_class(cls):
        shutil.rmtree("test/resources/test_collect_bugs_python_out")
        assert not os.path.exists("test/resources/test_collect_bugs_python_out")

    def test_gitbugactions_pytest_test_repo(self):
        """
        Verifies that the pytest project bugs have been found

        repo: https://github.com/gitbugactions/gitbugactions-pytest-test-repo
        """
        with open(
            "test/resources/test_collect_bugs_python_out/gitbugactions-gitbugactions-pytest-test-repo.json",
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
                    assert len(data["non_code_patch"]) == 0
                    assert data["commit_message"] == "fix sum\n"
                    assert data["commit_timestamp"] == "2023-06-09T20:06:31+00:00Z"
                    assert (
                        data["previous_commit_hash"]
                        == "fd90a022e97988819f93abdc8828dd75e5f50776"
                    )
                    assert data["previous_commit_message"] == "initial implementation\n"
                    assert (
                        data["previous_commit_timestamp"]
                        == "2023-06-09T20:05:56+00:00Z"
                    )
                    assert data["time_to_patch"] == "0:00:35"
                    assert data["strategy"] == "PASS_PASS"
                    assert len(data["bug_patch_file_extensions"]) == 1
                    assert "py" in data["bug_patch_file_extensions"]
                    assert len(data["test_patch_file_extensions"]) == 1
                    assert "py" in data["test_patch_file_extensions"]
                    assert len(data["non_code_patch_file_extensions"]) == 0
                    assert data["change_type"] == "SOURCE_ONLY"
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
                    assert len(data["non_code_patch"]) > 0
                    assert len(data["bug_patch"]) == 0
                    assert data["commit_message"] == "fix pi\n"
                    assert data["commit_timestamp"] == "2023-07-03T09:33:35+00:00Z"
                    assert (
                        data["previous_commit_hash"]
                        == "3b1fba52bb74343dfd2466446cbfd94f1f1700f9"
                    )
                    assert data["previous_commit_message"] == "implement pi\n"
                    assert (
                        data["previous_commit_timestamp"]
                        == "2023-07-03T09:32:44+00:00Z"
                    )
                    assert data["time_to_patch"] == "0:00:51"
                    assert data["strategy"] == "FAIL_PASS"
                    assert len(data["bug_patch_file_extensions"]) == 0
                    assert len(data["test_patch_file_extensions"]) == 0
                    assert len(data["non_code_patch_file_extensions"]) == 1
                    assert "txt" in data["non_code_patch_file_extensions"]
                    assert data["change_type"] == "NON_CODE_ONLY"
                    assert len(data["actions_runs"]) == 3
                    assert len(data["actions_runs"][0][0]["tests"]) == 13
                    assert len(data["actions_runs"][2][0]["tests"]) == 13

                elif data["commit_hash"] == "05e841e86b09a60324dd77aa6d247bfa6331ad9e":
                    assert len(data["non_code_patch"]) > 0
                    assert data["commit_message"] == "fix golden\n"
                    assert data["commit_timestamp"] == "2023-07-03T09:39:47+00:00Z"
                    assert (
                        data["previous_commit_hash"]
                        == "cb83f8851cc1a4f30bef7e096c22caba10cb450f"
                    )
                    assert data["previous_commit_message"] == "implement golden\n"
                    assert (
                        data["previous_commit_timestamp"]
                        == "2023-07-03T09:39:24+00:00Z"
                    )
                    assert data["time_to_patch"] == "0:00:23"
                    assert data["strategy"] == "FAIL_PASS"
                    assert len(data["bug_patch_file_extensions"]) == 1
                    assert "py" in data["bug_patch_file_extensions"]
                    assert len(data["test_patch_file_extensions"]) == 0
                    assert len(data["non_code_patch_file_extensions"]) == 1
                    assert "txt" in data["non_code_patch_file_extensions"]
                    assert data["change_type"] == "MIXED"
                    assert len(data["actions_runs"]) == 3
                    assert len(data["actions_runs"][0][0]["tests"]) == 15
                    assert len(data["actions_runs"][2][0]["tests"]) == 15

    def test_gitbugactions_unittest_test_repo(self):
        """
        Verifies that the unittest project bugs have been found

        repo: https://github.com/gitbugactions/gitbugactions-unittest-test-repo
        """
        with open(
            "test/resources/test_collect_bugs_python_out/gitbugactions-gitbugactions-unittest-test-repo.json",
            "r",
        ) as f:
            lines = f.readlines()
            assert len(lines) == 1
            data = json.loads(lines[0])
            assert data["commit_hash"] == "d3d7a607e3a8abc330f8fd69f677284a9afaf650"
            assert data["commit_timestamp"] == "2023-06-20T14:54:30+00:00Z"
            assert data["commit_message"] == "fix sum\n"
            assert (
                data["previous_commit_hash"]
                == "73a8a00fc8bbbe0af1351b4e97682138a32981b2"
            )
            assert data["previous_commit_message"] == "initial implementation\n"
            assert data["previous_commit_timestamp"] == "2023-06-20T14:54:25+00:00Z"
            assert data["time_to_patch"] == "0:00:05"
            assert data["strategy"] == "PASS_PASS"
            assert len(data["bug_patch_file_extensions"]) == 1
            assert "py" in data["bug_patch_file_extensions"]
            assert len(data["test_patch_file_extensions"]) == 1
            assert "py" in data["test_patch_file_extensions"]
            assert len(data["non_code_patch_file_extensions"]) == 0
            assert data["change_type"] == "SOURCE_ONLY"
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

    def test_collected_data(self):
        """Test the data.json file for Python-related repositories"""
        with open(
            "test/resources/test_collect_bugs_python_out/data.json",
            "r",
        ) as f:
            data = json.load(f)
            # Check Python repositories
            assert data["gitbugactions/gitbugactions-pytest-test-repo"]["commits"] == 6
            assert (
                data["gitbugactions/gitbugactions-unittest-test-repo"]["commits"] == 2
            )
            assert (
                data["gitbugactions/gitbugactions-pytest-test-repo"][
                    "possible_bug_patches"
                ]
                == 3
            )
            assert (
                data["gitbugactions/gitbugactions-unittest-test-repo"][
                    "possible_bug_patches"
                ]
                == 1
            )

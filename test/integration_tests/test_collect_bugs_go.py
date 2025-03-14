import os
import json
import shutil
from collect_bugs import collect_bugs
from test.integration_tests.test_collect_bugs import TestCollectBugs
import pytest


@pytest.mark.skip
class TestCollectBugsGo(TestCollectBugs):
    LANGUAGE = "go"

    @classmethod
    def setup_class(cls):
        super().setup_class()
        collect_bugs(
            "test/resources/test_collect_bugs_go",
            "test/resources/test_collect_bugs_go_out",
            4,
            strategies=["PASS_PASS", "FAIL_PASS", "FAIL_FAIL", "FAIL_PASS_BUILD"],
            filter_on_commit_time_start="2020-01-01 00:00 UTC",
        )

    @classmethod
    def teardown_class(cls):
        shutil.rmtree("test/resources/test_collect_bugs_go_out")
        assert not os.path.exists("test/resources/test_collect_bugs_go_out")

    def test_gitbugactions_go_test_repo(self):
        """
        Verifies that the go project bugs have been found

        repo: https://github.com/gitbugactions/gitbugactions-go-test-repo
        """
        with open(
            "test/resources/test_collect_bugs_out/gitbugactions-gitbugactions-go-test-repo.json",
            "r",
        ) as f:
            lines = f.readlines()
            assert len(lines) == 2
            for line in lines:
                data = json.loads(line)
                assert data["commit_hash"] in [
                    "c169aa04ee612b23ff9b3405260851c5ffa98e88",
                    "862faa2fe219817eab67de0a95c796f31fc595f1",
                ]

                if data["commit_hash"] == "c169aa04ee612b23ff9b3405260851c5ffa98e88":
                    assert data["commit_timestamp"] == "2023-07-21T16:48:15+00:00Z"
                    assert data["commit_message"] == "fix subtract\n"
                    assert (
                        data["previous_commit_hash"]
                        == "5cd82572d2ecf9fdd20bea5f4602ded6b3608b54"
                    )
                    assert data["previous_commit_message"] == "initial commit\n"
                    assert (
                        data["previous_commit_timestamp"]
                        == "2023-07-21T16:47:50+00:00Z"
                    )
                    assert data["time_to_patch"] == "0:00:25"
                    assert data["strategy"] == "FAIL_PASS"
                    assert len(data["bug_patch_file_extensions"]) == 1
                    assert "go" in data["bug_patch_file_extensions"]
                    assert len(data["test_patch_file_extensions"]) == 0
                    assert len(data["non_code_patch_file_extensions"]) == 0
                    assert data["change_type"] == "SOURCE_ONLY"
                    # assert that number of total tests before == 2 and one fails
                    assert len(data["actions_runs"][0][0]["tests"]) == 2
                    assert (
                        len(
                            [
                                x
                                for x in [
                                    r
                                    for _ in [
                                        y["results"]
                                        for y in data["actions_runs"][0][0]["tests"]
                                    ]
                                    for r in _
                                ]
                                if x["result"] == "Passed"
                            ]
                        )
                        == 1
                    )
                    assert (
                        len(
                            [
                                x
                                for x in [
                                    r
                                    for _ in [
                                        y["results"]
                                        for y in data["actions_runs"][0][0]["tests"]
                                    ]
                                    for r in _
                                ]
                                if x["result"] == "Failure"
                            ]
                        )
                        == 1
                    )
                    # assert that number of total tests after == 2 and all pass
                    assert len(data["actions_runs"][2][0]["tests"]) == 2
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

                if data["commit_hash"] == "862faa2fe219817eab67de0a95c796f31fc595f1":
                    assert data["commit_timestamp"] == "2023-07-22T10:20:51+00:00Z"
                    assert data["commit_message"] == "fix multiply\n"
                    assert (
                        data["previous_commit_hash"]
                        == "e383979ee1e98cac1681d4321f32ad6c9087b24f"
                    )
                    assert data["previous_commit_message"] == "implement multiply\n"
                    assert (
                        data["previous_commit_timestamp"]
                        == "2023-07-22T10:20:28+00:00Z"
                    )
                    assert data["time_to_patch"] == "0:00:23"
                    assert data["strategy"] == "PASS_PASS"
                    assert len(data["bug_patch_file_extensions"]) == 1
                    assert "go" in data["bug_patch_file_extensions"]
                    assert len(data["test_patch_file_extensions"]) == 1
                    assert "go" in data["test_patch_file_extensions"]
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
                                    y["results"]
                                    for y in data["actions_runs"][0][0]["tests"]
                                ]
                                for r in _
                            ]
                        ]
                    )
                    # assert that number of total tests w/ new tests == 3 and one fails
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
                                    y["results"]
                                    for y in data["actions_runs"][2][0]["tests"]
                                ]
                                for r in _
                            ]
                        ]
                    )

    def test_collected_data(self):
        """Test the data.json file for Go-related repositories"""
        with open(
            "test/resources/test_collect_bugs_go_out/data.json",
            "r",
        ) as f:
            data = json.load(f)
            # Check Go repositories
            assert data["gitbugactions/gitbugactions-go-test-repo"]["commits"] == 2
            assert (
                data["gitbugactions/gitbugactions-go-test-repo"]["possible_bug_patches"]
                == 2
            )

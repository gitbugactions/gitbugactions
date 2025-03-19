import os
import json
import shutil
from collect_bugs import collect_bugs
from test.integration_tests.test_collect_bugs import TestCollectBugs


class TestCollectBugsJava(TestCollectBugs):
    LANGUAGE = "java"

    @classmethod
    def setup_class(cls):
        super().setup_class()
        collect_bugs(
            "test/resources/test_collect_bugs_java",
            "test/resources/test_collect_bugs_java_out",
            4,
            strategies=["PASS_PASS", "FAIL_PASS", "FAIL_FAIL", "FAIL_PASS_BUILD"],
            filter_on_commit_time_start="2020-01-01 00:00 UTC",
            pull_requests=True,
            use_default_actions=True,
        )

    @classmethod
    def teardown_class(cls):
        shutil.rmtree("test/resources/test_collect_bugs_java_out")
        assert not os.path.exists("test/resources/test_collect_bugs_java_out")

    def test_gitbugactions_maven_test_repo(self):
        """
        Verifies that the maven project bugs have been found

        repo: https://github.com/gitbugactions/gitbugactions-maven-test-repo
        """
        with open(
            "test/resources/test_collect_bugs_java_out/gitbugactions-gitbugactions-maven-test-repo.json",
            "r",
        ) as f:
            lines = f.readlines()
            assert len(lines) == 6

            for line in lines:
                data = json.loads(line)
                assert data["commit_hash"] in [
                    "ef34d133079591972a5ce9442cbcc7603003d938",
                    "7e11161b4983f8ff9fd056fa465c8cabaa8a7f80",
                    "629f67ebc0efeeb8868a13ad173f18ec572a8729",
                    "37113cf952bd6d3db563d0d15beae07daefd953e",
                    "dc71f8ddba909f2c0c58324dd6e2c37a48c35f7f",
                    "ff6e2662174af4024eef123b7d23b15192748b31",
                    "dc71f8ddba909f2c0c58324dd6e2c37a48c35f7f",
                ]

                if data["commit_hash"] == "ef34d133079591972a5ce9442cbcc7603003d938":
                    assert data["commit_message"] == "Fix sum\n"
                    assert data["commit_timestamp"] == "2023-06-05T13:19:21+00:00Z"
                    assert (
                        data["previous_commit_hash"]
                        == "cad6744850817b708400736678d2601cbd1c1dd6"
                    )
                    assert data["previous_commit_message"] == "Add gitignore\n"
                    assert (
                        data["previous_commit_timestamp"]
                        == "2023-06-05T13:19:12+00:00Z"
                    )
                    assert data["time_to_patch"] == "0:00:09"
                    assert data["strategy"] == "PASS_PASS"
                    assert len(data["bug_patch_file_extensions"]) == 1
                    assert "java" in data["bug_patch_file_extensions"]
                    assert len(data["test_patch_file_extensions"]) == 1
                    assert "java" in data["test_patch_file_extensions"]
                    assert len(data["non_code_patch_file_extensions"]) == 0
                    assert data["change_type"] == "SOURCE_ONLY"
                    assert len(data["actions_runs"]) == 3
                    assert data["actions_runs"][0][0]["default_actions"]
                    assert data["actions_runs"][1][0]["default_actions"]
                    assert len(data["actions_runs"][1][0]["tests"]) == 1
                    assert len(data["actions_runs"][1][0]["tests"][0]["results"]) == 1
                    assert (
                        data["actions_runs"][1][0]["tests"][0]["results"][0]["result"]
                        == "Failure"
                    )
                    assert data["actions_runs"][2][0]["default_actions"]
                    assert data["commit_timestamp"] == "2023-06-05T13:19:21+00:00Z"

    def test_gitbugactions_gradle_test_repo(self):
        """
        Verifies that the gradle project bugs have been found

        repo: https://github.com/gitbugactions/gitbugactions-gradle-test-repo
        """
        with open(
            "test/resources/test_collect_bugs_java_out/gitbugactions-gitbugactions-gradle-test-repo.json",
            "r",
        ) as f:
            lines = f.readlines()
            assert len(lines) == 1
            data = json.loads(lines[0])
            assert data["commit_hash"] == "2289b33a322f01b95405905c53770a63fa21b8bf"
            assert data["commit_message"] == "fix sum\n"
            assert data["commit_timestamp"] == "2023-06-10T15:07:36+00:00Z"
            assert (
                data["previous_commit_hash"]
                == "cab2445ecf7788bed39802d716ae095fc499cafa"
            )
            assert data["previous_commit_message"] == "initial implementation\n"
            assert data["previous_commit_timestamp"] == "2023-06-10T15:07:10+00:00Z"
            assert data["time_to_patch"] == "0:00:26"
            assert data["strategy"] == "PASS_PASS"
            assert len(data["bug_patch_file_extensions"]) == 1
            assert "java" in data["bug_patch_file_extensions"]
            assert len(data["test_patch_file_extensions"]) == 1
            assert "java" in data["test_patch_file_extensions"]
            assert len(data["non_code_patch_file_extensions"]) == 0
            assert data["change_type"] == "SOURCE_ONLY"
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

    def test_collected_data(self):
        """Test the data.json file for Java-related repositories"""
        with open(
            "test/resources/test_collect_bugs_java_out/data.json",
            "r",
        ) as f:
            data = json.load(f)
            # Check Java repositories
            assert data["gitbugactions/gitbugactions-maven-test-repo"]["commits"] == 13
            assert data["gitbugactions/gitbugactions-gradle-test-repo"]["commits"] == 2
            assert (
                data["gitbugactions/gitbugactions-maven-test-repo"][
                    "possible_bug_patches"
                ]
                == 6
            )
            assert (
                data["gitbugactions/gitbugactions-gradle-test-repo"][
                    "possible_bug_patches"
                ]
                == 1
            )

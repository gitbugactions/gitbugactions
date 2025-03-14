import os
import json
import shutil
from collect_bugs import collect_bugs
from test.integration_tests.test_collect_bugs import TestCollectBugs


class TestCollectBugsJavaScript(TestCollectBugs):
    LANGUAGE = "javascript"

    @classmethod
    def setup_class(cls):
        super().setup_class()
        collect_bugs(
            "test/resources/test_collect_bugs_javascript",
            "test/resources/test_collect_bugs_javascript_out",
            4,
            strategies=["PASS_PASS", "FAIL_PASS", "FAIL_FAIL", "FAIL_PASS_BUILD"],
            filter_on_commit_time_start="2020-01-01 00:00 UTC",
        )

    @classmethod
    def teardown_class(cls):
        shutil.rmtree("test/resources/test_collect_bugs_javascript_out")
        assert not os.path.exists("test/resources/test_collect_bugs_javascript_out")

    def test_gitbugactions_npm_jest_test_repo(self):
        """
        Verifies that the npm-jest project bugs have been found

        repo: https://github.com/gitbugactions/gitbugactions-npm-jest-test-repo
        """
        with open(
            "test/resources/test_collect_bugs_javascript_out/gitbugactions-gitbugactions-npm-jest-test-repo.json",
            "r",
        ) as f:
            lines = f.readlines()
            assert len(lines) == 2

            for line in lines:
                data = json.loads(line)
                assert data["commit_hash"] in [
                    "fa9d952976eff56860653f15bbc62766ff4211a5",
                    "88399e528e6fb9a87a9f74e3bf9f6bf413577ebe",
                ]

                if data["commit_hash"] == "fa9d952976eff56860653f15bbc62766ff4211a5":
                    assert len(data["non_code_patch"]) == 0
                    assert data["commit_message"] == "fix subtract\n"
                    assert data["commit_timestamp"] == "2025-01-27T17:25:25+00:00Z"
                    assert (
                        data["previous_commit_hash"]
                        == "9b7db8411e1cfafae9b9a0720213e45d42ef394f"
                    )
                    assert data["previous_commit_message"] == "break subtract\n"
                    assert (
                        data["previous_commit_timestamp"]
                        == "2025-01-27T17:25:02+00:00Z"
                    )
                    assert data["time_to_patch"] == "0:00:23"
                    assert data["strategy"] == "FAIL_PASS"
                    assert len(data["bug_patch_file_extensions"]) == 1
                    assert len(data["test_patch_file_extensions"]) == 0
                    assert len(data["non_code_patch_file_extensions"]) == 0
                    assert data["change_type"] == "SOURCE_ONLY"
                    assert len(data["actions_runs"]) == 3
                    assert len(data["actions_runs"][0][0]["tests"]) == 5
                    assert len(data["actions_runs"][2][0]["tests"]) == 5

                elif data["commit_hash"] == "88399e528e6fb9a87a9f74e3bf9f6bf413577ebe":
                    assert len(data["non_code_patch"]) == 0
                    assert data["commit_message"] == "fix sum\n"
                    assert data["commit_timestamp"] == "2025-01-27T17:24:30+00:00Z"
                    assert (
                        data["previous_commit_hash"]
                        == "bad1d309fdcc0ebaf367690599480c0a38df54db"
                    )
                    assert data["previous_commit_message"] == "initial commit\n"
                    assert (
                        data["previous_commit_timestamp"]
                        == "2025-01-27T17:23:07+00:00Z"
                    )
                    assert data["time_to_patch"] == "0:01:23"
                    assert data["strategy"] == "PASS_PASS"
                    assert "js" in data["bug_patch_file_extensions"]
                    assert len(data["bug_patch_file_extensions"]) == 1
                    assert "js" in data["bug_patch_file_extensions"]
                    assert len(data["test_patch_file_extensions"]) == 1
                    assert len(data["non_code_patch_file_extensions"]) == 0
                    assert data["change_type"] == "SOURCE_ONLY"
                    assert len(data["actions_runs"]) == 3
                    assert len(data["actions_runs"][0][0]["tests"]) == 5
                    assert len(data["actions_runs"][1][0]["tests"]) == 5
                    assert len(data["actions_runs"][2][0]["tests"]) == 5

    def test_gitbugactions_npm_mocha_test_repo(self):
        """
        Verifies that the npm-mocha project bugs have been found

        repo: https://github.com/gitbugactions/gitbugactions-npm-mocha-test-repo
        """
        with open(
            "test/resources/test_collect_bugs_javascript_out/gitbugactions-gitbugactions-npm-mocha-test-repo.json",
            "r",
        ) as f:
            lines = f.readlines()
            assert len(lines) == 1

            for line in lines:
                data = json.loads(line)
                assert data["commit_hash"] in [
                    "3e3b7e364c478bd3a9e3d22d6b296f6f8ac0dfbf",
                ]
                assert data["strategy"] == "FAIL_PASS"

    def test_gitbugactions_npm_vitest_test_repo(self):
        """
        Verifies that the npm-vitest project bugs have been found

        repo: https://github.com/gitbugactions/gitbugactions-npm-vitest-test-repo
        """
        with open(
            "test/resources/test_collect_bugs_javascript_out/gitbugactions-gitbugactions-npm-vitest-test-repo.json",
            "r",
        ) as f:
            lines = f.readlines()
            assert len(lines) == 1

            for line in lines:
                data = json.loads(line)
                assert data["commit_hash"] in [
                    "708eb9c4935e65d673b84e226ceb513ae446c280",
                ]
                assert data["strategy"] == "FAIL_PASS"

    def test_collected_data(self):
        """Test the data.json file for JavaScript-related repositories"""
        with open(
            "test/resources/test_collect_bugs_javascript_out/data.json",
            "r",
        ) as f:
            data = json.load(f)
            # Check JavaScript repositories
            assert (
                data["gitbugactions/gitbugactions-npm-jest-test-repo"]["commits"] == 4
            )
            assert (
                data["gitbugactions/gitbugactions-npm-mocha-test-repo"]["commits"] == 2
            )
            assert (
                data["gitbugactions/gitbugactions-npm-vitest-test-repo"]["commits"] == 2
            )
            assert (
                data["gitbugactions/gitbugactions-npm-jest-test-repo"][
                    "possible_bug_patches"
                ]
                == 2
            )
            assert (
                data["gitbugactions/gitbugactions-npm-mocha-test-repo"][
                    "possible_bug_patches"
                ]
                == 1
            )
            assert (
                data["gitbugactions/gitbugactions-npm-vitest-test-repo"][
                    "possible_bug_patches"
                ]
                == 1
            )

import os
import json
import shutil
from collect_bugs import collect_bugs
from test.integration_tests.test_collect_bugs import TestCollectBugs


class TestCollectBugsTypeScript(TestCollectBugs):
    LANGUAGE = "typescript"

    @classmethod
    def setup_class(cls):
        super().setup_class()
        collect_bugs(
            "test/resources/test_collect_bugs_typescript",
            "test/resources/test_collect_bugs_typescript_out",
            4,
            strategies=["PASS_PASS", "FAIL_PASS", "FAIL_FAIL", "FAIL_PASS_BUILD"],
            filter_on_commit_time_start="2020-01-01 00:00 UTC",
        )

    @classmethod
    def teardown_class(cls):
        shutil.rmtree("test/resources/test_collect_bugs_typescript_out")
        assert not os.path.exists("test/resources/test_collect_bugs_typescript_out")

    def test_gitbugactions_ts_npm_jest_test_repo(self):
        """
        Verifies that the typescript-npm-jest project bugs have been found

        repo: https://github.com/gitbugactions/gitbugactions-ts-npm-jest-test-repo
        """
        with open(
            "test/resources/test_collect_bugs_typescript_out/gitbugactions-gitbugactions-ts-npm-jest-test-repo.json",
            "r",
        ) as f:
            lines = f.readlines()
            assert len(lines) == 1

            for line in lines:
                data = json.loads(line)
                assert data["commit_hash"] in [
                    "79b223e1d3ab707170eb6da68796c40d1c791236",
                ]
                assert data["strategy"] == "FAIL_PASS"

    def test_collected_data(self):
        """Test the data.json file for TypeScript-related repositories"""
        with open(
            "test/resources/test_collect_bugs_typescript_out/data.json",
            "r",
        ) as f:
            data = json.load(f)
            # Check TypeScript repositories
            assert (
                data["gitbugactions/gitbugactions-ts-npm-jest-test-repo"]["commits"]
                == 2
            )
            assert (
                data["gitbugactions/gitbugactions-ts-npm-jest-test-repo"][
                    "possible_bug_patches"
                ]
                == 1
            )

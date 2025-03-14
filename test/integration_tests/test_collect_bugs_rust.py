import os
import json
import shutil
from collect_bugs import collect_bugs
from test.integration_tests.test_collect_bugs import TestCollectBugs


class TestCollectBugsRust(TestCollectBugs):
    LANGUAGE = "rust"

    @classmethod
    def setup_class(cls):
        super().setup_class()
        collect_bugs(
            "test/resources/test_collect_bugs_rust",
            "test/resources/test_collect_bugs_rust_out",
            4,
            strategies=["PASS_PASS", "FAIL_PASS", "FAIL_FAIL", "FAIL_PASS_BUILD"],
            filter_on_commit_time_start="2020-01-01 00:00 UTC",
        )

    @classmethod
    def teardown_class(cls):
        shutil.rmtree("test/resources/test_collect_bugs_rust_out")
        assert not os.path.exists("test/resources/test_collect_bugs_rust_out")

    def test_gitbugactions_rust_test_repo(self):
        """
        Verifies that the rust project bugs have been found

        repo: https://github.com/gitbugactions/gitbugactions-rust-test-repo
        """
        with open(
            "test/resources/test_collect_bugs_rust_out/gitbugactions-gitbugactions-rust-test-repo.json",
            "r",
        ) as f:
            lines = f.readlines()
            assert len(lines) == 1

            for line in lines:
                data = json.loads(line)
                assert data["commit_hash"] in [
                    "45043fc05cce16a6da87a3a536f4adc900c5e967",
                ]
                assert data["strategy"] == "FAIL_PASS"

    def test_collected_data(self):
        """Test the data.json file for Rust-related repositories"""
        with open(
            "test/resources/test_collect_bugs_rust_out/data.json",
            "r",
        ) as f:
            data = json.load(f)
            # Check Rust repositories
            assert data["gitbugactions/gitbugactions-rust-test-repo"]["commits"] == 2
            assert (
                data["gitbugactions/gitbugactions-rust-test-repo"][
                    "possible_bug_patches"
                ]
                == 1
            )

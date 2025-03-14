import os
import json
import shutil
from collect_bugs import collect_bugs
from test.integration_tests.test_collect_bugs import TestCollectBugs


class TestCollectBugsCSharp(TestCollectBugs):
    LANGUAGE = "csharp"

    @classmethod
    def setup_class(cls):
        super().setup_class()
        collect_bugs(
            "test/resources/test_collect_bugs_csharp",
            "test/resources/test_collect_bugs_csharp_out",
            4,
            strategies=["PASS_PASS", "FAIL_PASS", "FAIL_FAIL", "FAIL_PASS_BUILD"],
            filter_on_commit_time_start="2020-01-01 00:00 UTC",
        )

    @classmethod
    def teardown_class(cls):
        shutil.rmtree("test/resources/test_collect_bugs_csharp_out")
        assert not os.path.exists("test/resources/test_collect_bugs_csharp_out")

    def test_gitbugactions_dotnet_test_repo(self):
        """
        Verifies that the dotnet project bugs have been found

        repo: https://github.com/gitbugactions/gitbugactions-dotnet-test-repo
        """
        with open(
            "test/resources/test_collect_bugs_csharp_out/gitbugactions-gitbugactions-dotnet-test-repo.json",
            "r",
        ) as f:
            lines = f.readlines()
            assert len(lines) == 1

            for line in lines:
                data = json.loads(line)
                assert data["commit_hash"] in [
                    "65b86c6855427d96067519b75a7bd41b093a2b2f",
                ]
                assert data["strategy"] == "FAIL_PASS"

    def test_collected_data(self):
        """Test the data.json file for C#-related repositories"""
        with open(
            "test/resources/test_collect_bugs_csharp_out/data.json",
            "r",
        ) as f:
            data = json.load(f)
            # Check C# repositories
            assert data["gitbugactions/gitbugactions-dotnet-test-repo"]["commits"] == 2
            assert (
                data["gitbugactions/gitbugactions-dotnet-test-repo"][
                    "possible_bug_patches"
                ]
                == 1
            )

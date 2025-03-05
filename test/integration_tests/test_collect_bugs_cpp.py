import os
import json
import shutil
from unidiff import PatchSet
from collect_bugs import collect_bugs
from gitbugactions.github_api import GithubToken
from gitbugactions.collect_bugs.collection_strategies import *


def get_token_usage():
    token_usage = 0
    if GithubToken.has_tokens():
        for token in GithubToken._GithubToken__TOKENS:
            token_usage += token.core_rate_limiter.requests
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

class TestCollectBugs:
    TOKEN_USAGE: int = 0

    @classmethod
    def setup_class(cls):
        GithubToken.init_tokens()
        TestCollectBugs.TOKEN_USAGE = get_token_usage()
        collect_bugs(
            "test/resources/test_collect_bugs_cpp",
            "test/resources/test_collect_bugs_cpp_out",
            4,
            strategies=["PASS_PASS", "FAIL_PASS", "FAIL_FAIL", "FAIL_PASS_BUILD"],
            filter_on_commit_time_start="2020-01-01 00:00 UTC",
            pull_requests=True,
        )

    @classmethod
    def teardown_class(cls):
        shutil.rmtree("test/resources/test_collect_bugs_cpp_out")
        assert not os.path.exists("test/resources/test_collect_bugs_cpp_out")

    def test_gitbugactions_c_cmake_test_repo(self):
        """
        Verifies that the c-cmake project bugs have been found

        repo: https://github.com/kuchungmsft/gitbugactions-c-cmake-test-repo
        """
        with open(
            "test/resources/test_collect_bugs_cpp_out/kuchungmsft-gitbugactions-c-cmake-test-repo.json",
            "r",
        ) as f:
            lines = f.readlines()
            assert len(lines) == 3

            for line in lines:
                data = json.loads(line)
                assert data["commit_hash"] in [
                    "ab267f32024cc6cb9e1b7478c67ad4937dbdda9b",
                    "5598359dd9e873ca2839ec8efc358e68516a51d9",
                    "720e4913a4de1ac244f103309eac130c773819ba"
                ]
                if data["commit_hash"] == "ab267f32024cc6cb9e1b7478c67ad4937dbdda9b":
                    assert len(PatchSet(data["non_code_patch"])) == 0
                    assert data["commit_message"] == "Fix add\n"
                    assert data["commit_timestamp"] == "2025-03-05T00:45:29+00:00Z"
                    assert (
                        data["previous_commit_hash"]
                        == "468c657dfaee1150a0cce57440b1b9cd9edd2774"
                    )
                    assert data["previous_commit_message"] == "Initial commit\n"
                    assert (
                        data["previous_commit_timestamp"]
                        == "2025-03-05T00:42:40+00:00Z"
                    )
                    assert data["time_to_patch"] == "0:02:49"
                    assert len(data["bug_patch_file_extensions"]) == 1
                    assert data["bug_patch_file_extensions"][0] == "c"
                    assert len(data["test_patch_file_extensions"]) == 2
                    assert "null" in data["test_patch_file_extensions"]
                    assert "c" in data["test_patch_file_extensions"]
                    assert len(data["non_code_patch_file_extensions"]) == 0
                    assert data["change_type"] == "SOURCE_ONLY"
                    assert len(data["actions_runs"]) == 3
                    assert len(data["actions_runs"][0][0]["tests"]) == 0
                    assert len(data["actions_runs"][1][0]["tests"]) == 1
                    assert len(data["actions_runs"][2][0]["tests"]) == 1
                    assert data["strategy"] == "PASS_PASS"

                elif data["commit_hash"] == "5598359dd9e873ca2839ec8efc358e68516a51d9":
                    assert len(PatchSet(data["non_code_patch"])) == 0
                    assert data["commit_message"] == "Fix subtract\n"
                    assert data["commit_timestamp"] == "2025-03-05T00:47:45+00:00Z"
                    assert (
                        data["previous_commit_hash"]
                        == "d37e5c38214fcfe47787c5824ef028806146e8e8"
                    )
                    assert data["previous_commit_message"] == "Add subtract and test case\n"
                    assert (
                        data["previous_commit_timestamp"]
                        == "2025-03-05T00:47:23+00:00Z"
                    )
                    assert data["time_to_patch"] == "0:00:22"
                    assert len(data["bug_patch_file_extensions"]) == 1
                    assert data["bug_patch_file_extensions"][0] == "c"
                    assert len(data["test_patch_file_extensions"]) == 0
                    assert len(data["non_code_patch_file_extensions"]) == 0
                    assert data["change_type"] == "SOURCE_ONLY"
                    assert len(data["actions_runs"]) == 3
                    assert len(data["actions_runs"][0][0]["tests"]) == 2
                    assert len(data["actions_runs"][2][0]["tests"]) == 2
                    assert data["strategy"] == "FAIL_PASS"

                elif data["commit_hash"] == "720e4913a4de1ac244f103309eac130c773819ba":
                    assert len(PatchSet(data["non_code_patch"])) == 0
                    assert data["commit_message"] == "Fix divide\n"
                    assert data["commit_timestamp"] == "2025-03-05T00:49:41+00:00Z"
                    assert (
                        data["previous_commit_hash"]
                        == "59f0ba65ed73b202cae55cdb63455e0b6aa781ab"
                    )
                    assert data["previous_commit_message"] == "Add divide and test case\n"
                    assert (
                        data["previous_commit_timestamp"]
                        == "2025-03-05T00:49:06+00:00Z"
                    )
                    assert data["time_to_patch"] == "0:00:35"
                    assert len(data["bug_patch_file_extensions"]) == 1
                    assert data["bug_patch_file_extensions"][0] == "c"
                    assert len(data["test_patch_file_extensions"]) == 0
                    assert len(data["non_code_patch_file_extensions"]) == 0
                    assert data["change_type"] == "SOURCE_ONLY"
                    assert len(data["actions_runs"]) == 3
                    assert len(data["actions_runs"][0][0]["tests"]) == 3
                    assert len(data["actions_runs"][2][0]["tests"]) == 3
                    assert data["strategy"] == "FAIL_PASS"

    def test_gitbugactions_cpp_cmake_test_repo(self):
        """
        Verifies that the cpp-cmake project bugs have been found

        repo: https://github.com/kuchungmsft/gitbugactions-cpp-cmake-test-repo
        """
        with open(
            "test/resources/test_collect_bugs_cpp_out/kuchungmsft-gitbugactions-cpp-cmake-test-repo.json",
            "r",
        ) as f:
            lines = f.readlines()
            assert len(lines) == 4

            for line in lines:
                data = json.loads(line)
                assert data["commit_hash"] in [
                    "d7f556a4e8cabbdefe66a7bc48031a9c1c35ed18",
                    "1c27b9e954959e084bef596343c3abe0c9a55f83",
                    "a686dfb656600b5ae63a7edf09458945c9f22030",
                    "dec4c7dd853b34c179b5c380ca4b79dd8559b195"
                ]
                if data["commit_hash"] == "d7f556a4e8cabbdefe66a7bc48031a9c1c35ed18":
                    assert len(PatchSet(data["non_code_patch"])) == 0
                    assert data["commit_message"] == "Fix add\n"
                    assert data["commit_timestamp"] == "2025-03-05T01:49:22+00:00Z"
                    assert (
                        data["previous_commit_hash"]
                        == "cec5c9c703c5bf3cc4e6b069fcaf7191d4cb73de"
                    )
                    assert data["previous_commit_message"] == "Initial commit\n"
                    assert (
                        data["previous_commit_timestamp"]
                        == "2025-03-05T01:47:49+00:00Z"
                    )
                    assert data["time_to_patch"] == "0:01:33"
                    assert len(data["bug_patch_file_extensions"]) == 1
                    assert data["bug_patch_file_extensions"][0] == "cpp"
                    assert len(data["test_patch_file_extensions"]) == 0
                    assert len(data["non_code_patch_file_extensions"]) == 0
                    assert data["change_type"] == "SOURCE_ONLY"
                    assert len(data["actions_runs"]) == 3
                    assert len(data["actions_runs"][0][0]["tests"]) == 1
                    assert len(data["actions_runs"][2][0]["tests"]) == 1
                    assert data["strategy"] == "FAIL_PASS"

                elif data["commit_hash"] == "1c27b9e954959e084bef596343c3abe0c9a55f83":
                    assert len(PatchSet(data["non_code_patch"])) == 0
                    assert data["commit_message"] == "Fix multiply\n"
                    assert data["commit_timestamp"] == "2025-03-05T01:49:22+00:00Z"
                    assert (
                        data["previous_commit_hash"]
                        == "d2bae40e46f268cf7157c78b78e08b8f86f5a768"
                    )
                    assert data["previous_commit_message"] == "Add multiply\n"
                    assert (
                        data["previous_commit_timestamp"]
                        == "2025-03-05T01:49:22+00:00Z"
                    )
                    assert data["time_to_patch"] == "0:00:00"
                    assert len(data["bug_patch_file_extensions"]) == 1
                    assert data["bug_patch_file_extensions"][0] == "hpp"
                    assert len(data["test_patch_file_extensions"]) == 2
                    assert "cpp" in data["test_patch_file_extensions"]
                    assert "null" in data["test_patch_file_extensions"]
                    assert len(data["non_code_patch_file_extensions"]) == 0
                    assert data["change_type"] == "SOURCE_ONLY"
                    assert len(data["actions_runs"]) == 3
                    assert len(data["actions_runs"][0][0]["tests"]) == 2
                    assert len(data["actions_runs"][1][0]["tests"]) == 3
                    assert len(data["actions_runs"][2][0]["tests"]) == 3
                    assert data["strategy"] == "PASS_PASS"

                elif data["commit_hash"] == "a686dfb656600b5ae63a7edf09458945c9f22030":
                    assert len(PatchSet(data["non_code_patch"])) == 0
                    assert data["commit_message"] == "Fix divide\n"
                    assert data["commit_timestamp"] == "2025-03-05T01:49:22+00:00Z"
                    assert (
                        data["previous_commit_hash"]
                        == "f45df23c71929ff2e0fe450e45c338ea7ddecd93"
                    )
                    assert data["previous_commit_message"] == "Add divide\n"
                    assert (
                        data["previous_commit_timestamp"]
                        == "2025-03-05T01:49:22+00:00Z"
                    )
                    assert data["time_to_patch"] == "0:00:00"
                    assert len(data["bug_patch_file_extensions"]) == 1
                    assert data["bug_patch_file_extensions"][0] == "cc"
                    assert len(data["test_patch_file_extensions"]) == 0
                    assert len(data["non_code_patch_file_extensions"]) == 0
                    assert data["change_type"] == "SOURCE_ONLY"
                    assert len(data["actions_runs"]) == 3
                    assert len(data["actions_runs"][0][0]["tests"]) == 4
                    assert len(data["actions_runs"][2][0]["tests"]) == 4
                    assert data["strategy"] == "FAIL_PASS"

                elif data["commit_hash"] == "dec4c7dd853b34c179b5c380ca4b79dd8559b195":
                    assert len(PatchSet(data["non_code_patch"])) == 0
                    assert data["commit_message"] == "Fix subtract\n"
                    assert data["commit_timestamp"] == "2025-03-05T01:49:22+00:00Z"
                    assert (
                        data["previous_commit_hash"]
                        == "cdd0a7e8804e1abde6016b7e4aaf8fc588c9265f"
                    )
                    assert data["previous_commit_message"] == "Add subtract and test case\n"
                    assert (
                        data["previous_commit_timestamp"]
                        == "2025-03-05T01:49:22+00:00Z"
                    )
                    assert data["time_to_patch"] == "0:00:00"
                    assert len(data["bug_patch_file_extensions"]) == 1
                    assert data["bug_patch_file_extensions"][0] == "c"
                    assert len(data["test_patch_file_extensions"]) == 0
                    assert len(data["non_code_patch_file_extensions"]) == 0
                    assert data["change_type"] == "SOURCE_ONLY"
                    assert len(data["actions_runs"]) == 3
                    assert len(data["actions_runs"][0][0]["tests"]) == 2
                    assert len(data["actions_runs"][2][0]["tests"]) == 2
                    assert data["strategy"] == "FAIL_PASS"

    def test_collected_data(self):
        with open(
            "test/resources/test_collect_bugs_cpp_out/data.json",
            "r",
        ) as f:
            data = json.load(f)
            assert len(data.keys()) == 2
            assert (
                data["kuchungmsft/gitbugactions-c-cmake-test-repo"]["commits"]
                == 6
            )
            assert (
                data["kuchungmsft/gitbugactions-c-cmake-test-repo"][
                    "possible_bug_patches"
                ]
                == 3
            )
            assert (
                data["kuchungmsft/gitbugactions-cpp-cmake-test-repo"]["commits"]
                == 8
            )
            assert (
                data["kuchungmsft/gitbugactions-cpp-cmake-test-repo"][
                    "possible_bug_patches"
                ]
                == 4
            )

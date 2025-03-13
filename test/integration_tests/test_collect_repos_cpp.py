import json
import os
import pytest

from collect_repos import CollectReposStrategy
from gitbugactions.github_api import GithubAPI
from test_collect_repos import BaseCollectReposTest


class TestCollectReposCppCMake(BaseCollectReposTest):

    def test_collect_repos_c_cmake(self):
        api = GithubAPI()
        repo = api.get_repo("kuchungmsft/gitbugactions-c-cmake-test-repo")

        CollectReposStrategy(self.temp_folder).handle_repo(repo)
        data_file = os.path.join(
            self.temp_folder,
            "kuchungmsft-gitbugactions-c-cmake-test-repo.json",
        )

        assert os.path.exists(data_file)
        with open(data_file, "r") as f:
            data = json.load(f)
            assert data["language"] == "c"
            assert "number_of_test_actions" in data
            assert data["number_of_test_actions"] == 1
            assert "actions_successful" in data
            assert data["actions_successful"]
            assert data["number_of_actions"] == 1
            assert len(data["actions_build_tools"]) == 1
            assert data["actions_build_tools"][0] == "cmake"
            assert len(data["actions_test_build_tools"]) == 1
            assert data["actions_test_build_tools"][0] == "cmake"

    def test_collect_repos_cpp_cmake(self):
        api = GithubAPI()
        repo = api.get_repo("kuchungmsft/gitbugactions-cpp-cmake-test-repo")

        CollectReposStrategy(self.temp_folder).handle_repo(repo)
        data_file = os.path.join(
            self.temp_folder,
            "kuchungmsft-gitbugactions-cpp-cmake-test-repo.json",
        )

        assert os.path.exists(data_file)
        with open(data_file, "r") as f:
            data = json.load(f)
            assert data["language"] == "c++"
            assert "number_of_test_actions" in data
            assert data["number_of_test_actions"] == 1
            assert "actions_successful" in data
            assert data["actions_successful"]
            assert data["number_of_actions"] == 1
            assert len(data["actions_build_tools"]) == 1
            assert data["actions_build_tools"][0] == "cmake"
            assert len(data["actions_test_build_tools"]) == 1
            assert data["actions_test_build_tools"][0] == "cmake"

    @pytest.mark.skip(reason="Skipped due to long runtime.")
    @pytest.mark.parametrize(
        "repo_name, language, number_of_actions, number_of_test_actions, actions_successful, actions_build_tools, actions_test_build_tools, has_actions_run, has_tests",
        [
            (
                "AcademySoftwareFoundation/OpenImageIO",
                "c++",
                8,
                0,
                False,
                [
                    "unknown",
                    "unknown",
                    "unknown",
                    "unknown",
                    "unknown",
                    "unknown",
                    "unknown",
                    "unknown",
                ],
                [],
                False,
                False,
            ),
            ("acoustid/chromaprint", "c++", 1, 0, False, ["cmake"], [], False, False),
            (
                "andrewprock/pokerstove",
                "c++",
                1,
                1,
                True,
                ["cmake"],
                ["cmake"],
                True,
                True,
            ),
            (
                "arvidn/libtorrent",
                "c++",
                9,
                0,
                False,
                [
                    "cmake",
                    "unknown",
                    "unknown",
                    "unknown",
                    "unknown",
                    "unknown",
                    "unknown",
                    "unknown",
                    "unknown",
                ],
                [],
                False,
                False,
            ),
            (
                "bblanchon/ArduinoJson",
                "c++",
                3,
                0,
                False,
                ["unknown", "cmake", "unknown"],
                [],
                False,
                False,
            ),
            ("bitcoin/bitcoin", "c++", 1, 1, True, ["cmake"], ["cmake"], True, False),
            (
                "bulletphysics/bullet3",
                "c++",
                1,
                1,
                False,
                ["cmake"],
                ["cmake"],
                True,
                False,
            ),
            (
                "cpputest/cpputest",
                "c++",
                2,
                0,
                False,
                ["unknown", "cmake"],
                [],
                False,
                False,
            ),
            (
                "doctest/doctest",
                "c++",
                2,
                1,
                False,
                ["unknown", "cmake"],
                ["cmake"],
                True,
                False,
            ),
            ("edouarda/brigand", "c++", 1, 0, False, ["cmake"], [], False, False),
            (
                "fast-pack/FastPFOR",
                "c++",
                4,
                4,
                False,
                ["cmake", "cmake", "cmake", "cmake"],
                ["cmake", "cmake", "cmake", "cmake"],
                False,
                False,
            ),
            (
                "fmtlib/fmt",
                "c++",
                7,
                0,
                False,
                ["cmake", "unknown", "cmake", "cmake", "unknown", "cmake", "unknown"],
                [],
                False,
                False,
            ),
            (
                "foonathan/type_safe",
                "c++",
                2,
                1,
                True,
                ["cmake", "cmake"],
                ["cmake"],
                True,
                False,
            ),
            (
                "google/benchmark",
                "c++",
                11,
                1,
                False,
                [
                    "cmake",
                    "unknown",
                    "cmake",
                    "cmake",
                    "unknown",
                    "unknown",
                    "cmake",
                    "cmake",
                    "unknown",
                    "cmake",
                    "unknown",
                ],
                ["cmake"],
                True,
                False,
            ),
            (
                "google/bloaty",
                "c++",
                2,
                0,
                False,
                ["cmake", "unknown"],
                [],
                False,
                False,
            ),
            (
                "google/brotli",
                "typescript",
                5,
                0,
                False,
                ["unknown", "unknown", "unknown", "unknown", "unknown"],
                [],
                False,
                False,
            ),
            (
                "google/jsonnet",
                "jsonnet",
                3,
                0,
                False,
                ["unknown", "unknown", "unknown"],
                [],
                False,
                False,
            ),
            (
                "jarro2783/cxxopts",
                "c++",
                3,
                1,
                True,
                ["cmake", "cmake", "unknown"],
                ["cmake"],
                True,
                True,
            ),
            (
                "jlblancoc/nanoflann",
                "c++",
                2,
                0,
                False,
                ["cmake", "unknown"],
                [],
                False,
                False,
            ),
            (
                "kimwalisch/primesieve",
                "c++",
                1,
                1,
                False,
                ["cmake"],
                ["cmake"],
                True,
                True,
            ),
            (
                "lemire/EWAHBoolArray",
                "c++",
                7,
                3,
                False,
                ["cmake", "cmake", "cmake", "cmake", "cmake", "cmake", "unknown"],
                ["cmake", "cmake", "cmake"],
                False,
                False,
            ),
            (
                "libsndfile/libsndfile",
                "c",
                2,
                0,
                False,
                ["cmake", "unknown"],
                [],
                False,
                False,
            ),
            (
                "libspatialindex/libspatialindex",
                "c++",
                1,
                1,
                True,
                ["cmake"],
                ["cmake"],
                True,
                True,
            ),
            (
                "martinmoene/ring-span-lite",
                "c++",
                1,
                1,
                False,
                ["cmake"],
                ["cmake"],
                True,
                True,
            ),
            (
                "nlohmann/json",
                "c++",
                12,
                2,
                False,
                [
                    "unknown",
                    "cmake",
                    "unknown",
                    "unknown",
                    "unknown",
                    "cmake",
                    "unknown",
                    "unknown",
                    "unknown",
                    "cmake",
                    "unknown",
                    "unknown",
                ],
                ["cmake", "cmake"],
                False,
                False,
            ),
            (
                "open-source-parsers/jsoncpp",
                "c++",
                3,
                0,
                False,
                ["unknown", "unknown", "unknown"],
                [],
                False,
                False,
            ),
            (
                "opencv/opencv",
                "c++",
                3,
                0,
                False,
                ["unknown", "unknown", "cmake"],
                [],
                False,
                False,
            ),
            (
                "socketio/socket.io-client-cpp",
                "c++",
                1,
                0,
                False,
                ["unknown"],
                [],
                False,
                False,
            ),
            (
                "taskflow/taskflow",
                "c++",
                4,
                3,
                False,
                ["cmake", "cmake", "unknown", "cmake"],
                ["cmake", "cmake", "cmake"],
                False,
                False,
            ),
            (
                "yanyiwu/cppjieba",
                "c++",
                3,
                2,
                False,
                ["cmake", "cmake", "unknown"],
                ["cmake", "cmake"],
                False,
                False,
            ),
        ],
    )
    def test_collect_repos_cpp(
        self,
        repo_name,
        language,
        number_of_actions,
        number_of_test_actions,
        actions_successful,
        actions_build_tools,
        actions_test_build_tools,
        has_actions_run,
        has_tests,
    ):
        api = GithubAPI()
        repo = api.get_repo(repo_name)

        CollectReposStrategy(self.temp_folder).handle_repo(repo)
        data_file = os.path.join(
            self.temp_folder,
            repo_name.replace("/", "-") + ".json",
        )

        assert os.path.exists(data_file)
        with open(data_file, "r") as f:
            data = json.load(f)
            assert data["language"] == language
            assert "number_of_actions" in data
            assert data["number_of_actions"] == number_of_actions
            assert "number_of_test_actions" in data
            assert data["number_of_test_actions"] == number_of_test_actions
            assert "actions_successful" in data
            assert data["actions_successful"] == actions_successful
            assert "actions_build_tools" in data
            assert sorted(data["actions_build_tools"]) == sorted(actions_build_tools)
            assert "actions_test_build_tools" in data
            assert sorted(data["actions_test_build_tools"]) == sorted(
                actions_test_build_tools
            )
            if has_actions_run:
                assert "actions_run" in data
                if has_tests:
                    assert len(data["actions_run"]["tests"]) > 0
                else:
                    assert len(data["actions_run"]["tests"]) == 0
            else:
                assert "actions_run" not in data

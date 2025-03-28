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
        "repo_name, actions_test_build_tools, has_actions_run, has_tests, using_template_workflow",
        [
            ("acoustid/chromaprint", [], True, True, True),
            ("andrewprock/pokerstove", ["cmake"], True, True, False),
            ("bblanchon/ArduinoJson", [], True, True, True),
            ("CLRX/CLRX-mirror", [], True, True, True),
            ("cpputest/cpputest", [], True, True, True),
            ("doctest/doctest", ["cmake"], True, False, False),
            ("edouarda/brigand", [], True, True, True),
            ("facebook/yoga", [], True, True, True),
            (
                "fast-pack/FastPFOR",
                ["cmake", "cmake", "cmake", "cmake"],
                False,
                False,
                False,
            ),
            ("fmtlib/fmt", [], True, True, True),
            ("foonathan/type_safe", ["cmake"], True, False, False),
            ("google/benchmark", ["cmake"], True, False, False),
            ("google/bloaty", [], True, True, True),
            ("google/flatbuffers", [], True, True, True),
            ("jarro2783/cxxopts", ["cmake"], True, True, False),
            ("jlblancoc/nanoflann", [], True, True, True),
            ("lemire/EWAHBoolArray", ["cmake", "cmake", "cmake"], False, False, False),
            ("libsndfile/libsndfile", [], True, True, True),
            ("libspatialindex/libspatialindex", ["cmake"], True, True, False),
            ("libuv/libuv", ["cmake", "cmake"], False, False, False),
            ("martinmoene/ring-span-lite", [], True, True, True),
            ("open-source-parsers/jsoncpp", [], True, True, True),
            ("socketio/socket.io-client-cpp", [], True, True, True),
            ("yanyiwu/cppjieba", ["cmake", "cmake"], False, False, False),
        ],
    )
    def test_collect_repos_cpp(
        self,
        repo_name,
        actions_test_build_tools,
        has_actions_run,
        has_tests,
        using_template_workflow,
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
            assert data["using_template_workflow"] == using_template_workflow

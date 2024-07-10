import os
import shutil
import pytest
import json
import tempfile
from gitbugactions.github_api import GithubAPI
from collect_repos import CollectInfraReposStrategy


class TestCollectReposInfra:
    @classmethod
    def setup_class(cls):
        TestCollectReposInfra.temp_folder = (
            tempfile.gettempdir() + "/collect_repos_infra"
        )
        if not os.path.exists(TestCollectReposInfra.temp_folder):
            os.makedirs(TestCollectReposInfra.temp_folder)

    @classmethod
    def teardown_class(cls):
        if os.path.exists(TestCollectReposInfra.temp_folder):
            shutil.rmtree(TestCollectReposInfra.temp_folder)
        assert not os.path.exists(TestCollectReposInfra.temp_folder)

    def test_collect_repos_infra(self):
        api = GithubAPI()
        repo = api.get_repo("gitbugactions/gitbugactions-infra-test-repo")

        CollectInfraReposStrategy(TestCollectReposInfra.temp_folder).handle_repo(repo)
        data_file = os.path.join(
            TestCollectReposInfra.temp_folder,
            "gitbugactions-gitbugactions-infra-test-repo.json",
        )

        assert os.path.exists(data_file)
        with open(data_file, "r") as f:
            data = json.load(f)
            assert "infra_files" in data
            assert data["infra_files"] == 1
            assert "actions_successful" in data
            assert not data["actions_successful"]
            assert data["number_of_actions"] == 1

    def test_collect_repos_infra_no_files(self):
        api = GithubAPI()
        repo = api.get_repo("gitbugactions/gitbugactions-maven-test-repo")

        CollectInfraReposStrategy(TestCollectReposInfra.temp_folder).handle_repo(repo)
        data_file = os.path.join(
            TestCollectReposInfra.temp_folder,
            "gitbugactions-gitbugactions-maven-test-repo.json",
        )

        with open(data_file, "r") as f:
            data = json.load(f)
            assert "infra_files" in data
            assert data["infra_files"] == 0
            assert "actions_successful" in data
            assert data["actions_successful"] is None

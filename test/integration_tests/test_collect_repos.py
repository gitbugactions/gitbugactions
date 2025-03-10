import json
import os
import shutil
import pytest
import tempfile

from collect_repos import CollectInfraReposStrategy, CollectReposStrategy
from gitbugactions.github_api import GithubAPI


class BaseCollectReposTest:
    @classmethod
    def setup_class(cls):
        cls.temp_folder = tempfile.mkdtemp(prefix="collect_repos_")

    @classmethod
    def teardown_class(cls):
        if os.path.exists(cls.temp_folder):
            shutil.rmtree(cls.temp_folder)


class TestCollectReposInfra(BaseCollectReposTest):
    def test_collect_repos_infra(self):
        api = GithubAPI()
        repo = api.get_repo("gitbugactions/gitbugactions-infra-test-repo")

        CollectInfraReposStrategy(self.temp_folder).handle_repo(repo)
        data_file = os.path.join(
            self.temp_folder,
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

        CollectInfraReposStrategy(self.temp_folder).handle_repo(repo)
        data_file = os.path.join(
            self.temp_folder,
            "gitbugactions-gitbugactions-maven-test-repo.json",
        )

        with open(data_file, "r") as f:
            data = json.load(f)
            assert "infra_files" in data
            assert data["infra_files"] == 0
            assert "actions_successful" in data
            assert data["actions_successful"] is None


class TestCollectReposJavaScript(BaseCollectReposTest):
    def test_collect_repos_npm_jest(self):
        api = GithubAPI()
        repo = api.get_repo("gitbugactions/gitbugactions-npm-jest-test-repo")

        CollectReposStrategy(self.temp_folder).handle_repo(repo)
        data_file = os.path.join(
            self.temp_folder,
            "gitbugactions-gitbugactions-npm-jest-test-repo.json",
        )

        assert os.path.exists(data_file)
        with open(data_file, "r") as f:
            data = json.load(f)
            assert "number_of_test_actions" in data
            assert data["number_of_test_actions"] == 1
            assert "actions_successful" in data
            assert data["actions_successful"]
            assert data["number_of_actions"] == 1

    def test_collect_repos_npm_mocha(self):
        api = GithubAPI()
        repo = api.get_repo("gitbugactions/gitbugactions-npm-mocha-test-repo")

        CollectReposStrategy(self.temp_folder).handle_repo(repo)
        data_file = os.path.join(
            self.temp_folder,
            "gitbugactions-gitbugactions-npm-mocha-test-repo.json",
        )

        assert os.path.exists(data_file)
        with open(data_file, "r") as f:
            data = json.load(f)
            assert "number_of_test_actions" in data
            assert data["number_of_test_actions"] == 1
            assert "actions_successful" in data
            assert data["actions_successful"]
            assert data["number_of_actions"] == 1

    def test_collect_repos_npm_vitest(self):
        api = GithubAPI()
        repo = api.get_repo("gitbugactions/gitbugactions-npm-vitest-test-repo")

        CollectReposStrategy(self.temp_folder).handle_repo(repo)
        data_file = os.path.join(
            self.temp_folder,
            "gitbugactions-gitbugactions-npm-vitest-test-repo.json",
        )

        assert os.path.exists(data_file)
        with open(data_file, "r") as f:
            data = json.load(f)
            assert "number_of_test_actions" in data
            assert data["number_of_test_actions"] == 1
            assert "actions_successful" in data
            assert data["actions_successful"]
            assert data["number_of_actions"] == 1

    def test_collect_repos_rust(self):
        api = GithubAPI()
        repo = api.get_repo("gitbugactions/gitbugactions-rust-test-repo")

        CollectReposStrategy(self.temp_folder).handle_repo(repo)
        data_file = os.path.join(
            self.temp_folder,
            "gitbugactions-gitbugactions-rust-test-repo.json",
        )

        assert os.path.exists(data_file)
        with open(data_file, "r") as f:
            data = json.load(f)
            assert "number_of_test_actions" in data
            assert data["number_of_test_actions"] == 1
            assert "actions_successful" in data
            assert data["actions_successful"]
            assert data["number_of_actions"] == 1

    def test_collect_repos_typescript_jest(self):
        api = GithubAPI()
        repo = api.get_repo("gitbugactions/gitbugactions-ts-npm-jest-test-repo")

        CollectReposStrategy(self.temp_folder).handle_repo(repo)
        data_file = os.path.join(
            self.temp_folder,
            "gitbugactions-gitbugactions-ts-npm-jest-test-repo.json",
        )

        assert os.path.exists(data_file)
        with open(data_file, "r") as f:
            data = json.load(f)
            assert "number_of_test_actions" in data
            assert data["number_of_test_actions"] == 1
            assert "actions_successful" in data
            assert data["actions_successful"]
            assert data["number_of_actions"] == 1

    @pytest.mark.skip(
        reason="Skipped due to long runtime and possible changes in repo."
    )
    def test_collect_repos_test_repo(self):
        api = GithubAPI()
        repo = api.get_repo("Uniswap/smart-order-router")

        CollectReposStrategy(self.temp_folder).handle_repo(repo)
        data_file = os.path.join(
            self.temp_folder,
            "Uniswap-smart-order-router.json",
        )

        assert os.path.exists(data_file)
        with open(data_file, "r") as f:
            data = json.load(f)
            assert "number_of_test_actions" in data
            assert data["number_of_test_actions"] == 1
            assert "actions_successful" in data
            assert data["actions_successful"]
            assert data["number_of_actions"] == 5


class TestCollectReposCSharp(BaseCollectReposTest):

    def test_collect_repos_dotnet(self):
        api = GithubAPI()
        repo = api.get_repo("gitbugactions/gitbugactions-dotnet-test-repo")

        CollectReposStrategy(self.temp_folder).handle_repo(repo)
        data_file = os.path.join(
            self.temp_folder,
            "gitbugactions-gitbugactions-dotnet-test-repo.json",
        )

        assert os.path.exists(data_file)
        with open(data_file, "r") as f:
            data = json.load(f)
            assert "number_of_test_actions" in data
            assert data["number_of_test_actions"] == 1
            assert "actions_successful" in data
            assert data["actions_successful"]
            assert data["number_of_actions"] == 1

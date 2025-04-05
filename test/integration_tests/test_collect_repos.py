import json
import os
import shutil
import pytest
import tempfile
import subprocess
import time
from unittest.mock import patch
import logging

from collect_repos import CollectInfraReposStrategy, CollectReposStrategy, collect_repos
from gitbugactions.github_api import GithubAPI


class BaseCollectReposTest:
    @classmethod
    def setup_class(cls):
        cls.temp_folder = tempfile.mkdtemp(prefix="collect_repos_")

    @classmethod
    def teardown_class(cls):
        if os.path.exists(cls.temp_folder):
            shutil.rmtree(cls.temp_folder)
            pass


class TestCollectReposInfra(BaseCollectReposTest):
    def test_collect_repos_infra(self):
        api = GithubAPI()
        repo = api.get_repo("gitbugactions/gitbugactions-infra-test-repo")

        CollectInfraReposStrategy(
            self.temp_folder, use_template_workflows=False
        ).handle_repo(repo)
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

        CollectInfraReposStrategy(
            self.temp_folder, use_template_workflows=False
        ).handle_repo(repo)
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

        CollectReposStrategy(
            self.temp_folder, use_template_workflows=False
        ).handle_repo(repo)
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
            assert data["actions_run"]["tests"] is not None
            assert len(data["actions_run"]["tests"]) > 0

    def test_collect_repos_npm_mocha(self):
        api = GithubAPI()
        repo = api.get_repo("gitbugactions/gitbugactions-npm-mocha-test-repo")

        CollectReposStrategy(
            self.temp_folder, use_template_workflows=False
        ).handle_repo(repo)
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
            assert data["actions_run"]["tests"] is not None
            assert len(data["actions_run"]["tests"]) > 0

    def test_collect_repos_npm_vitest(self):
        api = GithubAPI()
        repo = api.get_repo("gitbugactions/gitbugactions-npm-vitest-test-repo")

        CollectReposStrategy(
            self.temp_folder, use_template_workflows=False
        ).handle_repo(repo)
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
            assert data["actions_run"]["tests"] is not None
            assert len(data["actions_run"]["tests"]) > 0

    def test_collect_repos_rust(self):
        api = GithubAPI()
        repo = api.get_repo("gitbugactions/gitbugactions-rust-test-repo")

        CollectReposStrategy(
            self.temp_folder, use_template_workflows=False
        ).handle_repo(repo)
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
            assert data["actions_run"]["tests"] is not None
            assert len(data["actions_run"]["tests"]) > 0

    def test_collect_repos_typescript_jest(self):
        api = GithubAPI()
        repo = api.get_repo("gitbugactions/gitbugactions-ts-npm-jest-test-repo")

        CollectReposStrategy(
            self.temp_folder, use_template_workflows=False
        ).handle_repo(repo)
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
            assert data["actions_run"]["tests"] is not None
            assert len(data["actions_run"]["tests"]) > 0

    @pytest.mark.skip(
        reason="Skipped due to long runtime and possible changes in repo."
    )
    def test_collect_repos_test_repo(self):
        api = GithubAPI()
        repo = api.get_repo("Uniswap/smart-order-router")

        CollectReposStrategy(
            self.temp_folder, use_template_workflows=False
        ).handle_repo(repo)
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
            assert data["actions_run"]["tests"] is not None
            assert len(data["actions_run"]["tests"]) > 0


class TestCollectReposCSharp(BaseCollectReposTest):

    def test_collect_repos_dotnet(self):
        api = GithubAPI()
        repo = api.get_repo("gitbugactions/gitbugactions-dotnet-test-repo")

        CollectReposStrategy(
            self.temp_folder, use_template_workflows=False
        ).handle_repo(repo)
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
            assert data["actions_run"]["tests"] is not None
            assert len(data["actions_run"]["tests"]) > 0

    def test_collect_repos_dotnet_with_template_workflows(self):
        api = GithubAPI()
        repo = api.get_repo("gitbugactions/gitbugactions-dotnet-test-repo-no-actions")

        CollectReposStrategy(self.temp_folder, use_template_workflows=True).handle_repo(
            repo
        )
        data_file = os.path.join(
            self.temp_folder,
            "gitbugactions-gitbugactions-dotnet-test-repo-no-actions.json",
        )

        assert os.path.exists(data_file)
        with open(data_file, "r") as f:
            data = json.load(f)
            assert "number_of_test_actions" in data
            assert "actions_successful" in data
            assert data["actions_successful"]
            assert data["actions_run"]["tests"] is not None
            assert len(data["actions_run"]["tests"]) > 0
            assert data["using_template_workflow"]


class TestCollectReposCLI(BaseCollectReposTest):
    """Test the repository collection script from the CLI endpoint"""

    def test_collect_repos_cli(self):
        """Test basic repository collection from CLI with a simple query"""
        # Use a small query to limit the number of repositories
        query = "user:gitbugactions language:c# fork:false"

        # Run the collect_repos function directly
        collect_repos(
            query=query,
            out_path=self.temp_folder,
            n_workers=1,
            use_template_workflows=True,
            cleanup_interval=1,  # there are two repos, so we should run cleanup once
            enable_cleanup=True,
        )

        # Check that at least one repository was collected
        files = os.listdir(self.temp_folder)
        assert len(files) == 2, "Expected 2 repository data files, but got {}".format(
            len(files)
        )

        # Check the content of the first file
        with open(os.path.join(self.temp_folder, files[0]), "r") as f:
            data = json.load(f)
            assert "repository" in data
            assert "actions_successful" in data
            assert "number_of_actions" in data

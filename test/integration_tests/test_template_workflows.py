import json
import os
import tempfile
import shutil
from unittest.mock import patch, MagicMock

from collect_repos import CollectReposStrategy
from gitbugactions.actions.templates.template_workflows import (
    TemplateWorkflowManager,
    is_using_template_workflow,
)
from gitbugactions.actions.templates.languages.base import LanguageTemplate


class TestTemplateWorkflows:
    @classmethod
    def setup_class(cls):
        cls.temp_folder = tempfile.mkdtemp(prefix="template_workflows_test_")

    @classmethod
    def teardown_class(cls):
        if os.path.exists(cls.temp_folder):
            shutil.rmtree(cls.temp_folder)
            pass

    def test_create_template_workflow(self):
        # Test creating template workflows for different languages
        languages = [
            "c#",
        ]

        for language in languages:
            repo_path = os.path.join(self.temp_folder, language)
            os.makedirs(repo_path, exist_ok=True)

            # Create the workflow using direct call
            workflow_path = TemplateWorkflowManager.create_temp_workflow(
                repo_path, language
            )

            assert workflow_path is not None
            assert os.path.exists(workflow_path)
            assert is_using_template_workflow(workflow_path)

            # Check file content
            with open(workflow_path, "r") as f:
                content = f.read()
                assert (
                    language.lower() in content.lower()
                    or language.replace("#", "sharp").lower() in content.lower()
                )

            # Manually clean up
            cleanup_result = TemplateWorkflowManager.remove_temp_workflow(workflow_path)
            assert cleanup_result is True

            # Verify cleanup happened
            assert not os.path.exists(workflow_path)

    def test_remove_temp_workflow(self):
        # Test the remove_temp_workflow method
        repo_path = os.path.join(self.temp_folder, "removal_test")
        os.makedirs(repo_path, exist_ok=True)

        # Create the workflow
        workflow_path = TemplateWorkflowManager.create_temp_workflow(repo_path, "c#")
        assert workflow_path is not None
        assert os.path.exists(workflow_path)

        # Test successful removal
        result = TemplateWorkflowManager.remove_temp_workflow(workflow_path)
        assert result is True
        assert not os.path.exists(workflow_path)

        # Test removing a non-existent file
        result = TemplateWorkflowManager.remove_temp_workflow(workflow_path)
        assert result is False

        # Test removing None
        result = TemplateWorkflowManager.remove_temp_workflow(None)
        assert result is False

    def test_unsupported_language(self):
        repo_path = os.path.join(self.temp_folder, "unsupported")
        os.makedirs(repo_path, exist_ok=True)

        # Test with unsupported language
        workflow_path = TemplateWorkflowManager.create_temp_workflow(
            repo_path, "unsupported_language"
        )
        assert workflow_path is None

    def test_template_registration(self):
        # Test registering a new template
        class CustomTemplate(LanguageTemplate):
            @classmethod
            def get_name(cls):
                return "custom"

        # Register the custom template
        TemplateWorkflowManager.register_template(CustomTemplate)

        # Verify it's registered
        assert "custom" in TemplateWorkflowManager._language_map
        assert (
            TemplateWorkflowManager.get_template_for_language("custom")
            == CustomTemplate
        )

        # Create a repo with a custom file
        repo_path = os.path.join(self.temp_folder, "custom_repo")
        os.makedirs(repo_path, exist_ok=True)
        with open(os.path.join(repo_path, "test.custom"), "w") as f:
            f.write("custom content")

        # Assert that the custom template is used
        assert CustomTemplate.get_name() in TemplateWorkflowManager._language_map
        assert (
            TemplateWorkflowManager.get_template_for_language("custom")
            == CustomTemplate
        )

    @patch("gitbugactions.github_api.GithubAPI")
    def test_repo_with_no_workflow(self, mock_github_api):
        # Create a mock repo with no workflows
        mock_repo = MagicMock()
        mock_repo.full_name = "test/repo-no-workflow"
        mock_repo.clone_url = "https://github.com/test/repo-no-workflow.git"
        mock_repo.language = "c#"
        mock_repo.stargazers_count = 10
        mock_repo.size = 100

        # Setup the repository directory structure
        repo_path = os.path.join(self.temp_folder, "test-repo-no-workflow")
        os.makedirs(repo_path, exist_ok=True)

        # Mock clone_repo to return a path rather than actually cloning
        with patch("collect_repos.clone_repo", return_value=repo_path):
            # Mock delete_repo_clone to prevent AttributeError
            with patch("collect_repos.delete_repo_clone"):
                # Mock ActCacheDirManager
                with patch(
                    "gitbugactions.actions.actions.ActCacheDirManager.acquire_act_cache_dir",
                    return_value="/tmp/act-cache",
                ):
                    # Mock GitHubActions
                    with patch("collect_repos.GitHubActions") as mock_actions:
                        # Setup mock actions instance to have no workflows initially
                        mock_actions_instance = MagicMock()
                        mock_actions_instance.workflows = []
                        mock_actions_instance.test_workflows = []

                        # On second creation (after template addition), have a test workflow
                        mock_actions_instance2 = MagicMock()
                        mock_actions_instance2.workflows = [MagicMock()]
                        mock_actions_instance2.test_workflows = [MagicMock()]

                        # Setup side effect so first call returns no workflows, second call returns the workflow
                        mock_actions.side_effect = [
                            mock_actions_instance,
                            mock_actions_instance2,
                        ]

                        # Mock run_workflow to return successful results
                        with patch("collect_repos.run_workflow") as mock_run_workflow:
                            mock_run_result = MagicMock()
                            mock_run_result.failed = False
                            mock_run_result.asdict.return_value = {"tests": []}
                            mock_run_workflow.return_value = mock_run_result

                            # Execute the strategy
                            strategy = CollectReposStrategy(
                                self.temp_folder, use_template_workflows=True
                            )
                            strategy.handle_repo(mock_repo)

                            # Check that a template workflow was used
                            result_file = os.path.join(
                                self.temp_folder, "test-repo-no-workflow.json"
                            )
                            assert os.path.exists(result_file)

                            with open(result_file, "r") as f:
                                data = json.load(f)
                                assert data["using_template_workflow"] is True
                                assert data["actions_successful"] is True

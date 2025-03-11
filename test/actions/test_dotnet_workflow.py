import unittest
from unittest.mock import MagicMock, patch
import yaml

from gitbugactions.actions.csharp.dotnet_workflow import DotNetWorkflow
from gitbugactions.actions.csharp.helpers import DotNetProjectAnalyzer


class TestDotNetWorkflow(unittest.TestCase):
    def setUp(self):
        # Sample workflow YAML
        workflow_yaml = """
        name: .NET Build and Test
        
        on:
          push:
            branches: [ main ]
          pull_request:
            branches: [ main ]
            
        jobs:
          build:
            runs-on: ubuntu-latest
            steps:
            - uses: actions/checkout@v2
            - name: Setup .NET
              uses: actions/setup-dotnet@v1
              with:
                dotnet-version: 6.0.x
            - name: Restore dependencies
              run: dotnet restore
            - name: Build
              run: dotnet build --no-restore
            - name: Test
              run: dotnet test --no-build
        """

        # Parse YAML to dict
        workflow_dict = yaml.safe_load(workflow_yaml)

        # Create DotNetWorkflow instance
        self.workflow = DotNetWorkflow("owner/repo")
        self.workflow.doc = workflow_dict  # Set the workflow document directly

    def test_is_test_command(self):
        # Test various commands to check if they are recognized as test commands
        self.assertTrue(self.workflow._is_test_command("dotnet test"))
        self.assertTrue(self.workflow._is_test_command("dotnet test --no-build"))
        self.assertTrue(
            self.workflow._is_test_command("dotnet test ./tests/MyProject.Tests")
        )
        self.assertFalse(self.workflow._is_test_command("dotnet build"))
        self.assertFalse(self.workflow._is_test_command("dotnet restore"))

    @patch.object(DotNetProjectAnalyzer, "analyze_repository")
    def test_instrument_test_steps(self, mock_analyze_repo):
        # Mock the project analysis
        mock_analyze_repo.return_value = ({"src"}, {"test"})

        # Mock GitHub API
        github_api = MagicMock()

        # Instrument the test steps with GitHub API
        self.workflow.instrument_test_steps(github_api)

        # Check if test command was properly instrumented
        test_step = self.workflow.doc["jobs"]["build"]["steps"][4]
        self.assertIn("JUnitXml.TestLogger", test_step["run"])
        self.assertIn(
            '--logger:"junit;LogFilePath=./TestResults/test-results.xml"',
            test_step["run"],
        )

    @patch.object(DotNetProjectAnalyzer, "analyze_repository")
    def test_get_project_structure(self, mock_analyze_repo):
        # Mock the project analysis
        mock_analyze_repo.return_value = ({"src/App", "src/Core"}, {"tests/UnitTests"})

        # Mock GitHub API
        github_api = MagicMock()

        # Get project structure
        source_dirs, test_dirs = self.workflow.get_project_structure(github_api)

        # Verify results
        self.assertEqual(source_dirs, {"src/App", "src/Core"})
        self.assertEqual(test_dirs, {"tests/UnitTests"})

        # Verify analyzer was created and used
        self.assertIsNotNone(self.workflow.analyzer)
        mock_analyze_repo.assert_called_once()

    @patch.object(DotNetProjectAnalyzer, "analyze_repository")
    def test_get_project_structure_cached(self, mock_analyze_repo):
        # Set cached values
        self.workflow.source_dirs = {"src/App"}
        self.workflow.test_dirs = {"tests/UnitTests"}

        # Mock GitHub API
        github_api = MagicMock()

        # Get project structure
        source_dirs, test_dirs = self.workflow.get_project_structure(github_api)

        # Verify cached results are returned
        self.assertEqual(source_dirs, {"src/App"})
        self.assertEqual(test_dirs, {"tests/UnitTests"})

        # Verify analyzer was not called
        mock_analyze_repo.assert_not_called()

    @patch.object(DotNetProjectAnalyzer, "analyze_repository")
    def test_get_project_structure_error(self, mock_analyze_repo):
        # Mock the project analysis to raise an exception
        mock_analyze_repo.side_effect = Exception("API error")

        # Mock GitHub API
        github_api = MagicMock()

        # Get project structure
        source_dirs, test_dirs = self.workflow.get_project_structure(github_api)

        # Verify default values are returned on error
        self.assertEqual(source_dirs, {"src", "."})
        self.assertEqual(test_dirs, {"test", "tests"})

    @patch.object(DotNetWorkflow, "get_project_structure")
    def test_get_source_directories(self, mock_get_structure):
        # Mock the project structure
        mock_get_structure.return_value = ({"src/App", "src/Core"}, {"tests/UnitTests"})

        # Mock GitHub API
        github_api = MagicMock()

        # Get source directories
        source_dirs = self.workflow.get_source_directories(github_api)

        # Verify results
        self.assertEqual(source_dirs, {"src/App", "src/Core"})

    @patch.object(DotNetWorkflow, "get_project_structure")
    def test_get_test_directories(self, mock_get_structure):
        # Mock the project structure
        mock_get_structure.return_value = ({"src/App", "src/Core"}, {"tests/UnitTests"})

        # Mock GitHub API
        github_api = MagicMock()

        # Get test directories
        test_dirs = self.workflow.get_test_directories(github_api)

        # Verify results
        self.assertEqual(test_dirs, {"tests/UnitTests"})


if __name__ == "__main__":
    unittest.main()

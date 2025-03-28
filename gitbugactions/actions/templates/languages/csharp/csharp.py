from typing import Dict, Any, List
from gitbugactions.actions.templates.languages.base import LanguageTemplate
from gitbugactions.actions.csharp.helpers.dotnet_project_analyzer import (
    DotNetProjectAnalyzer,
)


class CSharpTemplate(LanguageTemplate):
    """C# language template for GitHub Actions workflow"""

    @classmethod
    def get_name(cls) -> str:
        return "c#"

    @classmethod
    def get_workflow(cls, **kwargs) -> Dict[str, Any]:
        # Get the repo path from the kwargs
        if "repo_path" not in kwargs:
            raise ValueError("repo_path is required for C# template workflow")
        repo_path = kwargs.get("repo_path")

        # Get the test directories by inspecting the repo
        analyzer = DotNetProjectAnalyzer(repo_path)
        _, test_dirs = analyzer.analyze_repository()

        workflow = {
            "name": "C# Template Test",
            "on": "push",
            "jobs": {
                "test": {
                    "runs-on": "ubuntu-latest",
                    "steps": [
                        {"uses": "actions/checkout@v3"},
                        {
                            "name": "Setup .NET 9",
                            "uses": "actions/setup-dotnet@v3",
                            "with": {"dotnet-version": "9.0.x"},
                        },
                        {
                            "name": "Setup .NET 8",
                            "uses": "actions/setup-dotnet@v3",
                            "with": {"dotnet-version": "8.0.x"},
                        },
                        {
                            "name": "Setup .NET 6",
                            "uses": "actions/setup-dotnet@v3",
                            "with": {"dotnet-version": "6.0.x"},
                        },
                    ],
                }
            },
        }

        for test_dir in test_dirs:
            workflow["jobs"]["test"]["steps"].append(
                {
                    "name": f"Run tests in {test_dir}",
                    "run": f"dotnet test {test_dir}",
                }
            )

        return workflow

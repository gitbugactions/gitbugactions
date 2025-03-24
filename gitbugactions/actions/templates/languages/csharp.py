from typing import Dict, Any, List
from gitbugactions.actions.templates.languages.base import LanguageTemplate


class CSharpTemplate(LanguageTemplate):
    """C# language template for GitHub Actions workflow"""

    @classmethod
    def get_name(cls) -> str:
        return "c#"

    @classmethod
    def get_workflow(cls) -> Dict[str, Any]:
        return {
            "name": "C# Template Test",
            "on": "push",
            "jobs": {
                "test": {
                    "runs-on": "ubuntu-latest",
                    "steps": [
                        {"uses": "actions/checkout@v3"},
                        {
                            "name": "Setup .NET",
                            "uses": "actions/setup-dotnet@v3",
                            "with": {"dotnet-version": "9.0.x"},
                        },
                        {"name": "Install dependencies", "run": "dotnet restore"},
                        {"name": "Build", "run": "dotnet build"},
                        {"name": "Test", "run": "dotnet test"},
                    ],
                }
            },
        }

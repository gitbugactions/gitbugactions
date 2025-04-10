import os
from typing import Dict, Any, List

import yaml
from gitbugactions.actions.templates.languages.base import LanguageTemplate


class CMakeTemplate(LanguageTemplate):
    """CMake language template for GitHub Actions workflow"""

    @classmethod
    def get_name(cls) -> str:
        return "cmake"

    @classmethod
    def get_workflow(cls, **kwargs) -> Dict[str, Any]:
        path = os.path.join(os.path.dirname(__file__), "cmake.yml")
        with open(path, "r") as file:
            workflow_content = file.read()
            return yaml.safe_load(workflow_content)

    @classmethod
    def can_handle_repo(cls, repo_path: str) -> bool:
        # Check and see if there is a CMakeLists.txt file in the repo including subdirectories
        for root, _, files in os.walk(repo_path):
            if "CMakeLists.txt" in files:
                return True
        return False

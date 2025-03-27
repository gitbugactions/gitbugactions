from typing import Dict, Any, List


class LanguageTemplate:
    """Base class for language-specific workflow templates"""

    @classmethod
    def get_name(cls) -> str:
        """Get the name of the language this template supports"""
        raise NotImplementedError("Subclasses must implement get_name")

    @classmethod
    def get_workflow(cls, **kwargs) -> Dict[str, Any]:
        """Get the workflow template for this language"""
        raise NotImplementedError("Subclasses must implement get_workflow")

    @classmethod
    def can_handle_repo(cls, repo_path: str) -> bool:
        """Check if this template can handle the repository"""
        return True

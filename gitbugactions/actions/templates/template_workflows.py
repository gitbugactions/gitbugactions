import os
import yaml
import logging
import uuid

from typing import Optional, Dict, List, Type

# Import language templates from the languages module
from gitbugactions.actions.templates.languages import (
    LanguageTemplate,
    CSharpTemplate,
    CMakeTemplate,
    CTemplate,
    CppTemplate,
)


class TemplateWorkflowManager:
    """Manages creation and cleanup of template workflows"""

    # Register template classes here
    _templates: List[Type[LanguageTemplate]] = [
        CSharpTemplate,
        CMakeTemplate,
        CTemplate,
        CppTemplate,
    ]

    # Dictionary for fast language lookup
    _language_map: Dict[str, Type[LanguageTemplate]] = {
        template.get_name(): template for template in _templates
    }

    @classmethod
    def register_template(cls, template_class: Type[LanguageTemplate]) -> None:
        """Register a new template class"""
        cls._templates.append(template_class)
        cls._language_map[template_class.get_name()] = template_class
        logging.debug(f"Registered template for {template_class.get_name()}")

    @classmethod
    def get_template_for_language(
        cls, language: str
    ) -> Optional[Type[LanguageTemplate]]:
        """Get template class for a given language"""
        language = language.lower()
        return cls._language_map.get(language)

    @classmethod
    def create_temp_workflow(cls, repo_path: str, language: str) -> Optional[str]:
        """
        Creates a temporary workflow file

        Args:
            repo_path: Path to the repository
            language: Repository language

        Returns:
            Optional[str]: Path to the created workflow file or None if not supported
        """
        try:
            # Try to find template for language
            template_class = cls.get_template_for_language(language)

            if not template_class:
                logging.warning(
                    f"No template workflow available for language: {language}"
                )
                return None

            # Check if the template can handle this repo
            if not template_class.can_handle_repo(repo_path):
                logging.warning(
                    f"Template for {language} cannot handle this repository"
                )
                return None

            # Create GitHub workflows directory if it doesn't exist
            workflow_dir = os.path.join(repo_path, ".github", "workflows")
            os.makedirs(workflow_dir, exist_ok=True)

            # Create the template workflow file
            temp_workflow_path = os.path.join(
                workflow_dir, f"template-test-crawler.yml"
            )

            # Get the template for the language
            workflow_content = template_class.get_workflow(repo_path=repo_path)

            # Add a random UUID to the workflow name
            workflow_content["name"] = f"{workflow_content['name']}-{str(uuid.uuid4())}"

            # Write the workflow to file
            with open(temp_workflow_path, "w") as f:
                yaml.dump(workflow_content, f)

            logging.info(
                f"Created template workflow for {language} at {temp_workflow_path}"
            )
            return temp_workflow_path

        except Exception as e:
            logging.error(f"Error creating template workflow: {str(e)}")
            return None

    @classmethod
    def remove_temp_workflow(cls, workflow_path: Optional[str]) -> bool:
        """
        Removes a temporary workflow file

        Args:
            workflow_path: Path to the workflow file to remove

        Returns:
            bool: True if removal was successful, False otherwise
        """
        if workflow_path and os.path.exists(workflow_path):
            try:
                os.remove(workflow_path)
                logging.info(f"Removed template workflow: {workflow_path}")
                return True
            except Exception as e:
                logging.warning(f"Failed to remove template workflow: {e}")
                return False
        return False


def is_using_template_workflow(workflow_path: str) -> bool:
    """
    Check if a workflow is a template workflow created by this module

    Args:
        workflow_path: Path to the workflow file

    Returns:
        bool: True if it's a template workflow
    """
    return os.path.basename(workflow_path).startswith("template-test-crawler")

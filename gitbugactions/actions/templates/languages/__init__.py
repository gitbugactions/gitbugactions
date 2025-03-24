# Language-specific templates for GitHub Actions workflows
# Import all language templates here

from gitbugactions.actions.templates.languages.base import LanguageTemplate
from gitbugactions.actions.templates.languages.csharp import CSharpTemplate

# Export all templates for easy import
__all__ = [
    "LanguageTemplate",
    "CSharpTemplate",
]

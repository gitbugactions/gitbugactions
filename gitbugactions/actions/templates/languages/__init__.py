# Language-specific templates for GitHub Actions workflows
# Import all language templates here

from gitbugactions.actions.templates.languages.base import LanguageTemplate
from gitbugactions.actions.templates.languages.csharp.csharp import CSharpTemplate
from gitbugactions.actions.templates.languages.cmake.cmake import CMakeTemplate
from gitbugactions.actions.templates.languages.c.c import CTemplate
from gitbugactions.actions.templates.languages.cpp.cpp import CppTemplate

# Export all templates for easy import
__all__ = [
    "LanguageTemplate",
    "CSharpTemplate",
    "CMakeTemplate",
    "CTemplate",
    "CppTemplate",
]

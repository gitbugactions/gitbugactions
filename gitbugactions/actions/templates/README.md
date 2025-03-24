# Template Workflows

This module provides default template workflows for repositories that don't have GitHub Actions workflows defined. It uses a registry pattern with a modular, extensible design where each language template is in its own file.

## How it Works

The `TemplateWorkflowManager` class coordinates:

1. Template registration for each supported language
2. Language detection from repository contents
3. Workflow creation and cleanup

## Project Structure

```
templates/
├── __init__.py
├── README.md
├── template_workflows.py    # Main manager implementation
└── languages/               # Language template implementations
    ├── __init__.py
    ├── base.py              # Base template class
    ├── python.py
    ├── java.py
    ├── javascript.py
    ├── typescript.py
    ├── go.py
    ├── rust.py
    ├── csharp.py
    ├── cpp.py
    └── c.py
```

## Using Template Workflows

The most convenient way to use template workflows is with the context manager:

```python
from gitbugactions.actions.templates.template_workflows import TemplateWorkflowManager

# Create a temporary workflow that will be automatically cleaned up
with TemplateWorkflowManager.create_temp_workflow(repo_path, language) as workflow_path:
    if workflow_path:
        # Do something with the workflow
        pass
    # When the context exits, the workflow file is automatically removed
```

## Supported Languages

The following languages are currently supported:

- Python
- Java
- JavaScript
- TypeScript
- Go
- Rust
- C#
- C++
- C

## Adding a New Language Template

To add support for a new language, create a new file in the `languages` directory:

```python
# languages/mylanguage.py
from typing import Dict, Any, List
from gitbugactions.actions.templates.languages.base import LanguageTemplate

class MyLanguageTemplate(LanguageTemplate):
    """My language template for GitHub Actions workflow"""
    
    @classmethod
    def get_name(cls) -> str:
        return "mylanguage"
    
    @classmethod
    def get_workflow(cls) -> Dict[str, Any]:
        return {
            "name": "My Language Template Test",
            "on": "push",
            "jobs": {
                "test": {
                    "runs-on": "ubuntu-latest",
                    "steps": [
                        # Define your workflow steps here
                    ]
                }
            }
        }
       
    @classmethod
    def can_handle_repo(cls, repo_path: str) -> bool:
        # Optional: Add custom logic to determine if this template
        # can handle this specific repository structure
        return True
```

Then register it in the `languages/__init__.py` file:

```python
# Add to the imports
from gitbugactions.actions.templates.languages.mylanguage import MyLanguageTemplate

# Add to __all__
__all__ = [
    # ... existing templates ...
    'MyLanguageTemplate',
]
```

The template will be automatically registered with the `TemplateWorkflowManager`.

## Advanced Customization

You can customize template selection further by implementing a custom `can_handle_repo` method that examines the repository structure and determines if a specific template can handle it.

For more complex scenarios, you can also create entirely new template managers by following the pattern in `TemplateWorkflowManager`. 
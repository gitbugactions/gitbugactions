import os
from pathlib import Path
from typing import Dict
from dotenv import load_dotenv


def load_required_env_vars() -> Dict[str, str]:
    """Load required environment variables from .env file and validate their presence"""
    # First try to load from .env file
    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(env_path)

    required_vars = {"GITHUB_ACCESS_TOKEN": None, "ACT_PATH": None}

    # Check each required variable
    for var in required_vars:
        value = os.getenv(var)
        if not value:
            raise EnvironmentError(
                f"Required environment variable {var} is not set. Set it in .env file or environment."
            )
        required_vars[var] = value

    # Update PATH to include ACT_PATH directory
    act_path = required_vars["ACT_PATH"]
    if act_path:
        act_dir = str(Path(act_path).parent)
        os.environ["PATH"] = f"{act_dir}:{os.environ.get('PATH', '')}"

    return required_vars

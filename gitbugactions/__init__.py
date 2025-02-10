"""
GitBugActions - A tool that builds executable code datasets by leveraging GitHub Actions.
"""

import logging
from gitbugactions.utils.env_utils import load_required_env_vars

# Configure basic logging
logging.basicConfig(level=logging.INFO)

# Load environment variables when package is imported
try:
    env_vars = load_required_env_vars()
except EnvironmentError as e:
    logging.error(f"Environment setup error: {str(e)}")
    logging.error(
        "Please make sure to create a .env file or set the required environment variables:"
    )
    logging.error(
        "- GITHUB_ACCESS_TOKEN: GitHub access token with necessary permissions"
    )
    logging.error("- ACT_PATH: Full path to the act executable")
    raise

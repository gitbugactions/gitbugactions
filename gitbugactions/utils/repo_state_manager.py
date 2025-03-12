import os
import shutil
import subprocess
import logging
from typing import Optional

import pygit2


class RepoStateManager:
    @staticmethod
    def clean_untracked_files(repo: pygit2.Repository):
        """
        Clean untracked files using git clean.

        This removes all untracked files and directories, including .act-result.
        The -f flag forces removal, -d includes directories, and -x ignores .gitignore rules.
        """
        subprocess.run(
            ["git", "clean", "-f", "-d", "-x"],
            cwd=repo.workdir,
            capture_output=True,
        )

    @staticmethod
    def clean_act_result_dir(repo_workdir: str):
        """
        Remove .act-result directory if it exists.

        Note: This is only needed when you want to clean just the .act-result directory
        without cleaning all untracked files. If you're already calling clean_untracked_files
        or reset_to_commit, this method is redundant.
        """
        act_result_path = os.path.join(repo_workdir, ".act-result")
        if os.path.exists(act_result_path):
            try:
                shutil.rmtree(act_result_path)
            except Exception as e:
                logging.error(f"Error removing .act-result directory: {e}")

    @staticmethod
    def reset_to_commit(
        repo: pygit2.Repository, commit_id: Optional[pygit2.Oid] = None
    ):
        """
        Reset repository to a specific commit (if provided) and clean untracked files.

        This is a comprehensive cleanup method that:
        1. Resets to the specified commit if commit_id is provided
        2. Cleans all untracked files and directories, including .act-result
        """
        if commit_id:
            repo.reset(commit_id, pygit2.GIT_RESET_HARD)

        # Always clean untracked files
        RepoStateManager.clean_untracked_files(repo)

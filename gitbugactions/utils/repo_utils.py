import logging
import os
import shutil
import time
import traceback

import pygit2


def delete_repo_clone(repo_clone: pygit2.Repository):
    def retry_remove(function, path, excinfo):
        time.sleep(0.5)
        if os.path.exists(path) and os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.exists(path) and os.path.isfile(path):
            os.remove(path)

    repo_clone.free()
    if os.path.exists(repo_clone.workdir):
        shutil.rmtree(repo_clone.workdir, onexc=retry_remove)


def clone_repo(clone_url: str, path: str) -> pygit2.Repository:
    retries = 3
    for r in range(retries):
        try:
            repo_clone: pygit2.Repository = pygit2.clone_repository(clone_url, path)
            return repo_clone
        except pygit2.GitError as e:
            if r == retries - 1:
                logging.error(
                    f"Error while cloning {clone_url}: {traceback.format_exc()}"
                )
                raise e


def git_clean(repo: pygit2.Repository, force=True):
    # Get the status of the working directory
    status = repo.status()

    # Iterate over the status entries
    for filepath, status_flags in status.items():
        # Check if the file is untracked
        if status_flags == pygit2.GIT_STATUS_WT_NEW:
            full_path = os.path.join(repo.path, "..", filepath)

            try:
                if os.path.isdir(full_path) and not os.path.islink(full_path):
                    if force:
                        # Remove directory recursively
                        shutil.rmtree(full_path)
                else:
                    # Remove file or symbolic link
                    os.remove(full_path)
            except Exception as e:
                logging.error(f"Error removing {full_path}: {e}")

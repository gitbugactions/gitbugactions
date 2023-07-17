import os
import logging
import traceback
import yaml
import shutil
import time
import pygit2
import subprocess
from typing import Optional
from crawlergpt.actions.actions import GitHubActions
from enum import Enum


def delete_repo_clone(repo_clone: pygit2.Repository):
    def retry_remove(function, path, excinfo):
        time.sleep(0.5)
        if os.path.exists(path) and os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.exists(path) and os.path.isfile(path):
            os.remove(path)

    repo_clone.free()
    if os.path.exists(repo_clone.workdir):
        shutil.rmtree(repo_clone.workdir, onerror=retry_remove)


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


def get_default_github_actions(
    repo_clone: pygit2.Repository, first_commit: pygit2.Commit, language: str
) -> Optional[GitHubActions]:
    try:
        # Get first commit where workflows were added
        run = subprocess.run(
            f"git log --reverse --diff-filter=A -- .github/workflows",
            cwd=repo_clone.workdir,
            capture_output=True,
            shell=True,
        )
        stdout = run.stdout.decode("utf-8")
        first_workflow_commit = stdout.split("\n")[0].split(" ")[1].strip()
        first_workflow_commit = repo_clone.revparse_single(first_workflow_commit)
        # Get all commits starting on the first commit where workflows were added
        commits = [
            commit
            for commit in repo_clone.walk(
                repo_clone.head.target,
                pygit2.GIT_SORT_TOPOLOGICAL | pygit2.GIT_SORT_REVERSE,
            )
        ]
        for i, commit in enumerate(commits):
            if commit.hex == first_workflow_commit.hex:
                break
        commits = commits[i:]

        # Run commits to get first valid workflow
        for commit in commits:
            repo_clone.checkout_tree(commit)
            repo_clone.set_head(commit.oid)
            try:
                actions = GitHubActions(repo_clone.workdir, language)
                if len(actions.test_workflows) > 0:
                    return actions
            except yaml.YAMLError:
                continue
    finally:
        repo_clone.reset(first_commit.oid, pygit2.GIT_RESET_HARD)


class FileType(Enum):
    SOURCE = 0
    TESTS = 1
    NON_SOURCE = 2


def get_file_type(language: str, file_path: str) -> FileType:
    language_extensions = {
        "java": {"java"},
        "python": {"py"},
    }
    test_keywords = {"test", "tests"}

    if any([keyword in file_path.split(os.sep) for keyword in test_keywords]):
        return FileType.TESTS

    extension = (
        file_path.split(".")[-1] if "." in file_path else file_path.split(os.sep)[-1]
    )
    if extension in language_extensions[language]:
        return FileType.SOURCE
    else:
        return FileType.NON_SOURCE

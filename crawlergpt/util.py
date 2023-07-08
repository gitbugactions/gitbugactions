import os
import yaml
import shutil
import time
import pygit2
from typing import Optional
from crawlergpt.actions.actions import GitHubActions


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


def get_default_github_actions(
    repo_clone: pygit2.Repository, first_commit: pygit2.Commit, language: str
) -> Optional[GitHubActions]:
    try:
        for commit in repo_clone.walk(
            repo_clone.head.target,
            pygit2.GIT_SORT_TOPOLOGICAL | pygit2.GIT_SORT_REVERSE,
        ):
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

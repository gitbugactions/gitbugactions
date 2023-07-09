import os
import yaml
import shutil
import time
import pygit2
import subprocess
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
        # Get first commit where workflows were added
        run = subprocess.run(f'git log --reverse --diff-filter=A -- .github/workflows', 
                       cwd=repo_clone.workdir, capture_output=True, shell=True)
        stdout = run.stdout.decode("utf-8")
        first_workflow_commit = stdout.split('\n')[0].split(' ')[1].strip()
        first_workflow_commit = repo_clone.revparse_single(first_workflow_commit)
        # Get all commits starting on the first commit where workflows were added
        commits = [commit for commit in repo_clone.walk(repo_clone.head.target, 
                                                        pygit2.GIT_SORT_TOPOLOGICAL 
                                                        | pygit2.GIT_SORT_REVERSE)]
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

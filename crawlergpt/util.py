import os, re
import logging
import traceback
import yaml
import shutil
import time
import pygit2
import subprocess
from typing import Optional
from crawlergpt.actions.actions import GitHubActions
from crawlergpt.actions.actions import ActCacheDirManager
from crawlergpt.test_executor import TestExecutor


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
        act_cache_dir = ActCacheDirManager.acquire_act_cache_dir()
        # Get commits where workflows were changed by reverse order
        run = subprocess.run(
            f"git log --reverse --diff-filter=A -- .github/workflows",
            cwd=repo_clone.workdir,
            capture_output=True,
            shell=True,
        )
        stdout = run.stdout.decode("utf-8")
        # FIXME more restrict
        commits = re.findall("commit ([a-z0-9]*)", stdout)

        # Run commits to get first valid workflow
        for commit in commits:
            commit = repo_clone.revparse_single(commit)
            repo_clone.checkout_tree(commit)
            repo_clone.set_head(commit.oid)
            try:
                actions = GitHubActions(repo_clone.workdir, language)
                if len(actions.test_workflows) == 1:
                    executor = TestExecutor(
                        repo_clone, language, act_cache_dir, actions
                    )
                    runs = executor.run_tests()
                    if not runs[0].failed:
                        return actions
            except yaml.YAMLError:
                continue

        raise RuntimeError(f"{repo_clone.workdir} has no valid default actions.")
    finally:
        repo_clone.reset(first_commit.oid, pygit2.GIT_RESET_HARD)
        ActCacheDirManager.return_act_cache_dir(act_cache_dir)

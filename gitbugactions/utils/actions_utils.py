import os
import re
import shutil
import subprocess
import xml
from typing import Optional

import pygit2
import yaml

from gitbugactions.actions.actions import ActCacheDirManager, GitHubActions
from gitbugactions.test_executor import TestExecutor


def get_default_github_actions(
    repo_clone: pygit2.Repository, first_commit: pygit2.Commit, language: str
) -> Optional[GitHubActions]:
    act_cache_dir = ActCacheDirManager.acquire_act_cache_dir()
    try:
        head = repo_clone.revparse_single("HEAD")
        # Get commits where workflows were changed by reverse order
        run = subprocess.run(
            f"git log --reverse --diff-filter=AM -- .github/workflows",
            cwd=repo_clone.workdir,
            capture_output=True,
            shell=True,
        )
        stdout = run.stdout.decode("utf-8")
        commits = re.findall("^commit ([a-z0-9]*)", stdout, flags=re.MULTILINE)
        # We add the latest commit because it was the commit used to test
        # the actions in the collect_repos phase
        commits.append(str(head.id))

        # Run commits to get first valid workflow
        for commit in commits:
            subprocess.run(
                ["git", "checkout", "-f", commit],
                cwd=repo_clone.workdir,
                capture_output=True,
            )
            try:
                actions = GitHubActions(repo_clone.workdir, language)
                if len(actions.test_workflows) == 1:
                    executor = TestExecutor(
                        repo_clone, language, act_cache_dir, actions
                    )
                    runs = executor.run_tests()
                    # We check for the tests because it is the metric used
                    # to choose the repos that we will run
                    if len(runs[0].tests) > 0:
                        return actions
            except (yaml.YAMLError, xml.etree.ElementTree.ParseError):
                continue
            finally:
                repo_clone.reset(head.id, pygit2.GIT_RESET_HARD)
                subprocess.run(
                    ["git", "clean", "-f", "-d", "-x"],
                    cwd=repo_clone.workdir,
                    capture_output=True,
                )

        raise RuntimeError(f"{repo_clone.workdir} has no valid default actions.")
    finally:
        ActCacheDirManager.return_act_cache_dir(act_cache_dir)
        repo_clone.reset(first_commit.id, pygit2.GIT_RESET_HARD)
        if os.path.exists(os.path.join(repo_clone.workdir, ".act-result")):
            shutil.rmtree(os.path.join(repo_clone.workdir, ".act-result"))

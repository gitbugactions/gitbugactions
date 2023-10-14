import json, fire
import tempfile
import uuid
import pygit2
import tqdm
import docker
import logging, traceback
import os, sys, shutil

from crawlergpt.test_executor import TestExecutor
from crawlergpt.util import delete_repo_clone
from crawlergpt.docker.export import create_diff_image
from crawlergpt.actions.actions import ActCacheDirManager, ActTestsRun
from crawlergpt.github_token import GithubToken

from collect_bugs import BugPatch
from run_bug import get_default_actions, get_diff_path
from unidiff import PatchSet
from junitparser import TestCase
from typing import Callable, Optional, List, Dict
from github import Repository
from concurrent.futures import ThreadPoolExecutor, Future, as_completed


def run_commit(
    bug: BugPatch,
    repo_clone: pygit2.Repository,
    diff_folder_path: str,
    test_fn: Callable[[], Optional[List[ActTestsRun]]],
) -> Optional[List[ActTestsRun]]:
    docker_client = docker.from_env()
    act_cache_dir = ActCacheDirManager.acquire_act_cache_dir()
    image_name = f"crawlergpt-run-bug:{str(uuid.uuid4())}"

    try:
        create_diff_image(
            "crawlergpt:latest", image_name, get_diff_path(diff_folder_path)
        )
        executor = TestExecutor(
            repo_clone,
            bug.language,
            act_cache_dir,
            get_default_actions(diff_folder_path, repo_clone, bug.language),
            runner=image_name,
        )

        return test_fn(executor)
    finally:
        ActCacheDirManager.return_act_cache_dir(act_cache_dir)
        docker_client.images.remove(image_name)


def equal_test_results(old_test_results: List[Dict], new_test_results: List[TestCase]):
    def check_test(old_test: Dict, new_test: TestCase):
        # Different test
        if not (
            old_test["name"] == new_test.name
            and old_test["classname"] == new_test.classname
        ):
            return False
        # Test is passed
        if new_test.is_passed and old_test["results"][0]["result"] == "Passed":
            return True
        if len(old_test["results"]) != len(new_test.result):
            return False
        aux_new_test_result = list(new_test.result)
        for old_result in old_test["results"]:
            for i, new_result in enumerate(aux_new_test_result):
                if old_result["result"] == new_result.__class__.__name__:
                    aux_new_test_result.pop(i)
                    break
            else:
                return False
        return True

    if len(old_test_results) != len(new_test_results):
        return False

    aux_new_test_results = list(new_test_results)
    for old_test in old_test_results:
        for i, new_test in enumerate(aux_new_test_results):
            if check_test(old_test, new_test):
                aux_new_test_results.pop(i)
                break
        else:
            return False
    return True


def filter_bug(
    bug: Dict, repo: Repository, repo_clone: pygit2.Repository, export_path: str
) -> bool:
    try:
        repo_name = bug["repository"].replace("/", "-")
        bug_patch: BugPatch = BugPatch(
            repo,
            repo_clone.revparse_single(bug["commit_hash"]),
            repo_clone.revparse_single(bug["previous_commit_hash"]),
            PatchSet(bug["bug_patch"]),
            PatchSet(bug["test_patch"]),
            PatchSet(bug["non_code_patch"]),
            set(),
        )
        prev_diff_folder_path = os.path.join(
            export_path, repo_name, bug_patch.previous_commit
        )
        cur_diff_folder_path = os.path.join(export_path, repo_name, bug_patch.commit)

        for _ in range(5):
            run = run_commit(
                bug_patch,
                repo_clone,
                prev_diff_folder_path,
                bug_patch.test_previous_commit,
            )
            if not equal_test_results(bug["actions_runs"][0][0]["tests"], run[0].tests):
                return False

            if len(bug_patch.test_patch) > 0:
                run = run_commit(
                    bug_patch,
                    repo_clone,
                    prev_diff_folder_path,
                    bug_patch.test_previous_commit_with_diff,
                )
                if not equal_test_results(
                    bug["actions_runs"][1][0]["tests"], run[0].tests
                ):
                    return False

            run = run_commit(
                bug_patch,
                repo_clone,
                cur_diff_folder_path,
                bug_patch.test_current_commit,
            )
            if not equal_test_results(bug["actions_runs"][2][0]["tests"], run[0].tests):
                return False

        return True
    finally:
        delete_repo_clone(repo_clone)


def filter_bugs(bugs_path: str, export_path: str, res_path: str, n_workers=1):
    ActCacheDirManager.init_act_cache_dirs(n_dirs=n_workers)
    executor = ThreadPoolExecutor(max_workers=n_workers)
    github = GithubToken.get_token().github

    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        future_to_bug: Dict[Future, Dict] = {}

        for bugs_file in os.listdir(bugs_path):
            if bugs_file == "data.json" or not bugs_file.endswith(".json"):
                continue

            with open(os.path.join(bugs_path, bugs_file), "r") as f:
                bugs = list(filter(lambda line: len(line.strip()) != 0, f.readlines()))
                if len(bugs) == 0:
                    continue
            clone_url = json.loads(bugs[0])["clone_url"]
            repo = github.get_repo(json.loads(bugs[0])["repository"])
            repo_clone = pygit2.clone_repository(
                clone_url, os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
            )

            try:
                for bug in bugs:
                    bug = json.loads(bug)
                    new_repo_path = os.path.join(
                        tempfile.gettempdir(), str(uuid.uuid4())
                    )
                    shutil.copytree(repo_clone.workdir, new_repo_path, symlinks=True)
                    repo_clone_copy = pygit2.Repository(
                        os.path.join(new_repo_path, ".git")
                    )
                    future = executor.submit(
                        filter_bug, bug, repo, repo_clone_copy, export_path
                    )
                    future_to_bug[future] = bug
            finally:
                delete_repo_clone(repo_clone)

        for future in tqdm.tqdm(as_completed(future_to_bug), total=len(future_to_bug)):
            try:
                bug = future_to_bug[future]
                repository = bug["repository"]
                commit = bug["commit_hash"]
                non_flaky = future.result()
            except Exception:
                logging.error(
                    f"Error testing flakiness on {repository}@{commit}: {traceback.format_exc()}"
                )
            else:
                if non_flaky:
                    with open(os.path.join(res_path, "non-flaky.json"), "a") as f:
                        f.write(
                            json.dumps({"repository": repository, "commit": commit})
                        )
                else:
                    with open(os.path.join(res_path, "flaky.json"), "a") as f:
                        f.write(
                            json.dumps({"repository": repository, "commit": commit})
                        )


def main():
    fire.Fire(filter_bugs)


if __name__ == "__main__":
    sys.exit(main())

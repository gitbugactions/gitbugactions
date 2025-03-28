import json
import logging
import os
import shutil
import sys
import tempfile
import traceback
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional

import fire
import pygit2
import tqdm
from junitparser import TestCase
from pathlib import Path

from collect_bugs import BugPatch
from gitbugactions.actions.actions import Act, ActCacheDirManager, ActTestsRun
from gitbugactions.docker.client import DockerClient
from gitbugactions.docker.export import create_diff_image
from gitbugactions.test_executor import TestExecutor
from gitbugactions.utils.repo_utils import delete_repo_clone
from gitbugactions.utils.repo_state_manager import RepoStateManager
from run_bug import get_default_actions, get_diff_path


def run_commit(
    bug: BugPatch,
    repo_clone: pygit2.Repository,
    diff_folder_path: str,
    image_name: str,
    test_fn: Callable[[], Optional[List[ActTestsRun]]],
    offline: bool,
    use_default_actions: bool = False,
) -> Optional[List[ActTestsRun]]:
    act_cache_dir = ActCacheDirManager.acquire_act_cache_dir()
    try:
        # FIXME: we shouldn't need to call this here, but we have to do it because the get_default_actions script will inspect the repo state
        RepoStateManager.reset_to_commit(repo_clone, bug.commit)

        default_actions = None
        if use_default_actions:
            default_actions = get_default_actions(
                diff_folder_path, repo_clone, bug.language
            )

        executor = TestExecutor(
            repo_clone,
            bug.language,
            act_cache_dir,
            default_actions,
            runner_image=image_name,
        )

        return test_fn(executor, offline)
    except Exception as e:
        traceback.print_exc()
    finally:
        ActCacheDirManager.return_act_cache_dir(act_cache_dir)


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
    bug: Dict,
    repo_clone: pygit2.Repository,
    export_path: str,
    offline: bool,
    n_executions: int,
    base_image: str | None = None,
    use_default_actions: bool = False,
) -> str:
    try:
        repo_name = bug["repository"].replace("/", "-")
        bug_patch: BugPatch = BugPatch.from_dict(bug, repo_clone)
        diff_folder_path = os.path.join(export_path, repo_name, bug_patch.commit)

        Act(base_image=base_image)  # Pass base_image to Act initialization
        image_name = f"gitbugactions-run-bug:{str(uuid.uuid4())}"
        docker_client = DockerClient.getInstance()
        create_diff_image(
            "gitbugactions:latest", image_name, get_diff_path(diff_folder_path)
        )

        previous_commit_runs = []
        previous_commit_with_diff_runs = []
        current_commit_runs = []

        for _ in range(n_executions):
            run = run_commit(
                bug_patch,
                repo_clone,
                diff_folder_path,
                image_name,
                bug_patch.test_previous_commit,
                offline=offline,
                use_default_actions=use_default_actions,
            )
            previous_commit_runs.append(run)

            if len(bug_patch.test_patch) > 0:
                run = run_commit(
                    bug_patch,
                    repo_clone,
                    diff_folder_path,
                    image_name,
                    bug_patch.test_previous_commit_with_diff,
                    offline=offline,
                    use_default_actions=use_default_actions,
                )
                previous_commit_with_diff_runs.append(run)

            run = run_commit(
                bug_patch,
                repo_clone,
                diff_folder_path,
                image_name,
                bug_patch.test_current_commit,
                offline=offline,
                use_default_actions=use_default_actions,
            )
            current_commit_runs.append(run)

        # It is a fail if all runs are empty
        if (
            all(
                run[0].tests is None or len(run[0].tests) == 0
                for run in previous_commit_runs
            )
            or (
                len(bug_patch.test_patch) != 0
                and any(
                    run[0].tests is None or len(run[0].tests) == 0
                    for run in previous_commit_with_diff_runs
                )
            )
            or all(
                run[0].tests is None or len(run[0].tests) == 0
                for run in current_commit_runs
            )
        ):
            return "FAIL"
        # It is flaky if at least one is different
        elif (
            any(
                not equal_test_results(bug["actions_runs"][0][0]["tests"], run[0].tests)
                for run in previous_commit_runs
            )
            or (
                len(bug_patch.test_patch) != 0
                and any(
                    not equal_test_results(
                        bug["actions_runs"][1][0]["tests"], run[0].tests
                    )
                    for run in previous_commit_with_diff_runs
                )
            )
            or any(
                not equal_test_results(bug["actions_runs"][2][0]["tests"], run[0].tests)
                for run in current_commit_runs
            )
        ):
            return "FLAKY"
        # It is non-flaky if not all runs are empty and all are equal
        else:
            return "NON-FLAKY"
    finally:
        # delete_repo_clone(repo_clone)
        docker_client.images.remove(image_name, force=True)


def filter_bugs(
    bugs_path: str,
    export_path: str,
    res_path: str,
    n_workers: int = 1,
    offline: bool = True,
    n_executions: int = 5,
    base_image: str | None = None,
    use_default_actions: bool = False,
):
    """Creates the list of non-flaky bug-fixes that are able to be reproduced.

    Args:
        bugs_path (str): Folder where the result of collect_bugs is.
        export_path (str): Folder where the result of export_bugs is.
        res_path (str): Folder on which the results will be saved.
        n_workers (int, optional): Number of parallel workers. Defaults to 1.
        offline (bool, optional): If the containers must be isolated from the internet. Defaults to True.
        n_executions (int, optional): Number of times to execute each test. Defaults to 5.
        base_image (str, optional): Base image to use for building the runner image. If None, uses default.
        use_default_actions (bool, optional): Whether to use and collect default GitHub actions from repositories. Defaults to False.
    """
    ActCacheDirManager.init_act_cache_dirs(n_dirs=n_workers)
    executor = ThreadPoolExecutor(max_workers=n_workers)

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
                        filter_bug,
                        bug,
                        repo_clone_copy,
                        export_path,
                        offline,
                        n_executions,
                        base_image,
                        use_default_actions,
                    )
                    future_to_bug[future] = bug
            finally:
                # delete_repo_clone(repo_clone)
                pass

        for future in tqdm.tqdm(as_completed(future_to_bug), total=len(future_to_bug)):
            try:
                bug = future_to_bug[future]
                repository = bug["repository"]
                commit = bug["commit_hash"]
                status = future.result()
            except Exception:
                logging.error(
                    f"Error testing flakiness on {repository}@{commit}: {traceback.format_exc()}"
                )
            else:
                if not Path(res_path).exists():
                    Path(res_path).mkdir(parents=True, exist_ok=True)
                if status == "NON-FLAKY":
                    with open(os.path.join(res_path, "non-flaky.json"), "a") as f:
                        f.write(
                            json.dumps({"repository": repository, "commit": commit})
                            + "\n"
                        )
                elif status == "FAIL":
                    with open(os.path.join(res_path, "fail.json"), "a") as f:
                        f.write(
                            json.dumps({"repository": repository, "commit": commit})
                            + "\n"
                        )
                elif status == "FLAKY":
                    with open(os.path.join(res_path, "flaky.json"), "a") as f:
                        f.write(
                            json.dumps({"repository": repository, "commit": commit})
                            + "\n"
                        )


def main():
    fire.Fire(filter_bugs)


if __name__ == "__main__":
    sys.exit(main())

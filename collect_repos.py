import tempfile
import pygit2
import os, logging, sys, shutil, traceback
import json
import uuid
import fire
from datetime import datetime
from dataclasses import asdict
from github import Repository
from crawlergpt.util import delete_repo_clone
from crawlergpt.crawler import RepoStrategy, RepoCrawler
from crawlergpt.actions.actions import GitHubActions

class CollectReposStrategy(RepoStrategy):
    def __init__(self, data_path: str):
        self.data_path = data_path
        self.uuid = str(uuid.uuid1())


    def save_data(self, data: dict, repo):
        """
        Saves the data json to a file with the name of the repository
        """
        repo_name = repo.full_name.replace("/", "-")
        data_path = os.path.join(self.data_path, repo_name + ".json")
        with open(data_path, "w") as f:
            json.dump(data, f, indent=4)


    def handle_repo(self, repo: Repository):
        logging.info(f"Cloning {repo.full_name} - {repo.clone_url}")
        repo_path = os.path.join(tempfile.gettempdir(), self.uuid, repo.full_name.replace("/", "-"))

        data = {
            'repository': repo.full_name,
            'stars': repo.stargazers_count,
            'language': repo.language.strip().lower(),
            'size': repo.size,
            'clone_url': repo.clone_url,
            'timestamp': datetime.utcnow().isoformat() + "Z",
            'clone_success': False,
            'number_of_actions': 0,
            'number_of_test_actions': 0,
            'actions_successful': False
        }

        repo_clone = pygit2.clone_repository(
            repo.clone_url, 
            repo_path
        )

        try:
            data['clone_success'] = True

            actions = GitHubActions(repo_path, repo.language)
            data['number_of_actions'] = len(actions.workflows)
            data['actions_build_tools'] = [x.get_build_tool() for x in actions.workflows]
            data['number_of_test_actions'] = len(actions.test_workflows)
            data['actions_test_build_tools'] = [x.get_build_tool() for x in actions.test_workflows]
            actions.save_workflows()
            
            if len(actions.test_workflows) == 1:
                logging.info(f"Running actions for {repo.full_name}")

                # Act creates names for the containers by hashing the content of the workflows
                # To avoid conflicts between threads, we randomize the name
                actions.test_workflows[0].doc["name"] = str(uuid.uuid4())
                actions.save_workflows()

                # We need to set a different cache dir for each worker to avoid conflicts
                # See https://github.com/nektos/act/issues/1885 -> "act's git actions download cache isn't process / thread safe"
                act_cache_dir = os.path.join(tempfile.gettempdir(), "act-cache", str(uuid.uuid4()))
                try:
                    act_run = actions.run_workflow(actions.test_workflows[0], act_cache_dir=act_cache_dir)
                finally:
                    if os.path.exists(act_cache_dir):
                        shutil.rmtree(act_cache_dir, ignore_errors=True)

                data['actions_successful'] = not act_run.failed
                data['actions_run'] = asdict(act_run)
                data['actions_run']['tests'] = []
                for test in act_run.tests:
                    results = []
                    for result in test.result:
                        results.append({
                            'result': result.__class__.__name__,
                            'message': result.message,
                            'type': result.type
                        })
                    if len(results) == 0:
                        results.append({ 'result': 'Passed', 'message': '', 'type': '' })

                    data['actions_run']['tests'].append({
                        'classname': test.classname,
                        'name': test.name,
                        'time': test.time,
                        'results': results,
                        'stdout': test.system_out,
                        'stderr': test.system_err
                    })

            
            delete_repo_clone(repo_clone)
            self.save_data(data, repo)
        except Exception as e:
            logging.error(f"Error while processing {repo.full_name}: {traceback.format_exc()}")
            delete_repo_clone(repo_clone)
            self.save_data(data, repo)
        

def collect_repos(query: str, pagination_freq: str = 'M', n_workers: int = 1, out_path: str = "./out/"):
    crawler = RepoCrawler(query, pagination_freq=pagination_freq, n_workers=n_workers)
    crawler.get_repos(CollectReposStrategy(out_path))


def main():
    fire.Fire(collect_repos)

if __name__ == '__main__':
    sys.exit(main())

import tempfile
import pygit2
import os, logging
import json
import shutil
import uuid
from datetime import datetime
from github import Repository
from crawlergpt.crawler import RepoStrategy, RateLimiter, RepoCrawler
from crawlergpt.act import GitHubTestActions

class RunnableRepoStrategy(RepoStrategy):
    def __init__(self, data_path: str, rate_limiter: RateLimiter):
        self.data_path = data_path
        self.rate_lim = rate_limiter
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
            'clone_url': repo.clone_url,
            'timestamp': datetime.utcnow().isoformat() + "Z",
            'clone_success': False,
            'number of actions': 0,
            'number_of_test_actions': 0,
            'actions_successful': False
        }

        try:
            repo_clone = pygit2.clone_repository(
                repo.clone_url, 
                repo_path
            )
            data['clone_success'] = True

            test_actions = GitHubTestActions(repo_path)
            data['number of actions'] = len(test_actions.workflows)
            data['number_of_test_actions'] = len(test_actions.test_workflows)
            test_actions.save_workflows()
            
            if len(test_actions.test_workflows) == 1:
                logging.info(f"Running actions for {repo.full_name}")
                data['actions_successful'], data['actions_stdout'], data['actions_stderr'] = test_actions.get_failed_tests(test_actions.test_workflows[0])
                # FIXME check if we are able to get test reports
                data['actions_successful'] = data['actions_successful'] is not None
            
            if os.path.exists(repo_path):
                shutil.rmtree(repo_path)
            self.save_data(data, repo)
        except Exception as e:
            if os.path.exists(repo_path):
                shutil.rmtree(repo_path)
            self.save_data(data, repo)
        

if __name__ == '__main__':
    query = input()
    rate_limiter = RateLimiter()
    crawler = RepoCrawler(query, rate_limiter, pagination_freq='M', n_workers=int(input()))
    crawler.get_repos(RunnableRepoStrategy("./out/", rate_limiter))

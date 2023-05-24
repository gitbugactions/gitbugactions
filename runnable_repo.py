import tempfile
import pygit2
import os, logging
from github import Repository
from crawler import RepoStrategy, RateLimiter, RepoCrawler
from act import GitHubTestActions

class RunnableRepoStrategy(RepoStrategy):
    def __init__(self, data_path: str, rate_limiter: RateLimiter):
        self.rate_lim = rate_limiter

    def handle_repo(self, repo: Repository):
        logging.info(f"Cloning {repo.full_name} - {repo.clone_url}")
        repo_path = os.path.join(tempfile.gettempdir(), repo.name)
        repo_clone = pygit2.clone_repository(
            repo.clone_url, 
            repo_path
        )

        test_actions = GitHubTestActions(repo_path)
        test_actions.save_workflows()



if __name__ == '__main__':
    query = input()
    rate_limiter = RateLimiter()
    crawler = RepoCrawler(query, rate_limiter, pagination_freq='D')
    crawler.get_repos(RunnableRepoStrategy("out.jsonl", rate_limiter))
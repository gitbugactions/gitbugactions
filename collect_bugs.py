import os
import json
from github import Github
from crawler import BugCollectorStrategy, RateLimiter

bug_collector = BugCollectorStrategy("out.jsonl", rate_limiter=RateLimiter())
dir_list = os.listdir("out_50")

for file in dir_list:
    with open(f"out_50/{file}", "r") as f:
        run = json.loads(f.read())
        if run["actions_successful"] == False and run["number_of_test_actions"] == 1:
            github: Github = Github(
                login_or_token=os.environ["GITHUB_ACCESS_TOKEN"], 
                per_page=100, 
            )
            repo = github.get_repo(run["repository"])
            bug_collector.handle_repo(repo)

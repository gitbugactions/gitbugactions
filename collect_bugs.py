import os
import sys
import tqdm
import json
from github import Github
from crawler import BugCollectorStrategy, RateLimiter
from concurrent.futures import ThreadPoolExecutor, as_completed

rate_limiter = RateLimiter()
github: Github = Github(
    login_or_token=os.environ["GITHUB_ACCESS_TOKEN"], 
    per_page=100, 
)
dir_list = os.listdir("out_50")

if len(sys.argv) == 2:
    n_workers = int(sys.argv[1])
else:
    n_workers = 1

executor = ThreadPoolExecutor(max_workers=n_workers)
futures = []

for file in dir_list:
    with open(f"out_50/{file}", "r") as f:
        run = json.loads(f.read())
        name = run["repository"].replace("/", "-")
        if not os.path.exists("out_bugs"):
            os.mkdir("out_bugs")
        bug_collector = BugCollectorStrategy(f"out_bugs/{name}.jsonl", rate_limiter=rate_limiter)

        if run["actions_successful"] == False and run["number_of_test_actions"] == 1:
            repo = github.get_repo(run["repository"])
            args = (repo, )
            futures.append(executor.submit(bug_collector.handle_repo, *args))

for future in tqdm.tqdm(as_completed(futures)):
    future.result()

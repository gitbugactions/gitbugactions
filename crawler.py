import os
import re
import uuid
import json
import time
import math
import shutil
import pygit2
import tempfile
import logging
import tqdm
import pandas as pd
from unidiff import PatchSet
from abc import ABC, abstractmethod
from act import GitHubTestActions
from github import Github, Repository, RateLimitExceededException
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# FIXME change to custom logger
logging.basicConfig(level=logging.INFO)


class RateLimiter:
    __GITHUB_REQUESTS_LIMIT = 29 # The real limit is 30, but we try to avoid it
    __GITHUB_RESET_SECONDS = 60
    
    def __init__(self):
        self.requests = 0
        self.first_request = datetime.now()

    def request(self, fn, *args, **kwargs):
        retries = 3
        if self.requests == 0:
            self.first_request = datetime.now()
        elif (datetime.now() - self.first_request).total_seconds() > RateLimiter.__GITHUB_RESET_SECONDS:
            self.requests = 0
            self.first_request = datetime.now()
        if self.requests == RateLimiter.__GITHUB_REQUESTS_LIMIT:
            time.sleep(RateLimiter.__GITHUB_RESET_SECONDS)
            self.requests = 0
        self.requests += 1

        try:
            return fn(*args, **kwargs)
        except RateLimitExceededException as exc:
            logging.warning(f"Github Rate Limit Exceeded: {exc.headers}")
            reset_time = datetime.fromtimestamp(int(exc.headers["x-ratelimit-reset"]))
            retry_after = (reset_time - datetime.now()).total_seconds() + 1
            retry_after = max(retry_after, 0)  # In case we hit a negative total_seconds
            time.sleep(retry_after)
            retries -= 1
            if retries == 0:
                raise exc


class RepoStrategy(ABC):
    def __init__(self, data_path: str):
        self.data_path = data_path

    @abstractmethod
    def handle_repo(self, repo: Repository):
        pass


class BugCollectorStrategy(RepoStrategy):
    __FIX_ISSUE_REGEX = "(close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved) #([0-9]*)"

    def __init__(self, data_path: str, rate_limiter: RateLimiter, n_workers=1):
        super().__init__(data_path)
        self.rate_lim = rate_limiter

    def handle_repo(self, repo: Repository):
        logging.info(f"Cloning {repo.full_name} - {repo.clone_url}")
        repo_path = os.path.join(tempfile.gettempdir(), repo.full_name.replace('/', '-'))
        if os.path.exists(repo_path):
            shutil.rmtree(repo_path)
        repo_clone = pygit2.clone_repository(
            repo.clone_url, 
            repo_path
        )

        #FIXME
        has_junit = False
        for root, dirs, files in os.walk(repo_path):
            if "pom.xml" in files:
                with open(os.path.join(root, "pom.xml"), "r") as f:
                    if "junit" in f.read():
                        has_junit = True
                        break
        if not has_junit:
            return
        #

        test_actions = GitHubTestActions(repo_path)

        if len(list(repo_clone.references.iterator())) > 0:
            with open(self.data_path, "w") as fp:
                first_commit = None

                for commit in repo_clone.walk(repo_clone.head.target):
                    if first_commit is None:
                        first_commit = commit

                    if 'fix' not in commit.message.lower():
                        continue

                    # Use only commits with issues
                    # https://liuhuigmail.github.io/publishedPappers/TSE2022BugBuilder.pdf
                    # issues = re.findall(BugCollectorStrategy.__FIX_ISSUE_REGEX, commit.message)
                    # if len(issues) == 0:
                    #     continue

                    commit_hex = commit.hex
                    previous_commit_hex = commit.hex + '~1'
                    try:
                        previous_commit = repo_clone.revparse_single(previous_commit_hex)
                    except KeyError:
                        # The current commit is the first one
                        continue

                    data = { 
                        'repository': repo.full_name,
                        'clone_url': repo.clone_url,
                        'timestamp': datetime.utcnow().isoformat() + "Z",
                        'commit_hash': commit.hex,
                        'commit_message': commit.message,
                        'related_issues': '',
                        # 'failed_tests': failed_diff
                    }

                    # Bug Patch and Tests
                    diff = repo_clone.diff(previous_commit_hex, commit_hex)
                    patch = PatchSet(diff.patch)
                    bug_patch = PatchSet('')
                    test_patch = PatchSet('')

                    for p in patch:
                        if any([keyword in p.source_file.split(os.sep) for keyword in ['test', 'tests']]):
                            test_patch.append(p)
                        else:
                            bug_patch.append(p)

                    # Ignore commits without tests
                    if len(test_patch) == 0:
                        logging.info(f"Skipping commit {commit.hex}: no test patch")
                        continue

                    data['bug_patch'] = str(bug_patch)
                    data['test_patch'] = str(test_patch)

                    # Avoids some mentions to PRs
                    # issue_found = False

                    # for issue in issues:
                    #     if not issue[1].isdigit():
                    #         continue
                        
                    #     try:
                    #         gh_issue = self.rate_lim.request(repo.get_issue, number=int(issue[1]))
                    #         data['related_issues'] += f"\n Issue #{issue[1]} - {gh_issue.title}\n"
                    #         if gh_issue.body:
                    #             data['related_issues'] += str(gh_issue.body)
                    #         # Filter only bug issues
                    #         for label in gh_issue.labels:
                    #             if label.name == 'bug':
                    #                 issue_found = True
                    #                 break
                    #     except UnknownObjectException:
                    #         # The number of the issue mentioned does not exist
                    #         pass
                    #     except GithubException:
                    #         # Issues are disabled for this repo
                    #         break

                    # if not issue_found:
                    #     continue

                    previous_failed_tests = []
                    current_failed_tests = []
                    workflow_succeeded = False

                    for workflow in test_actions.test_workflows:
                        # Apply diff and run tests
                        repo_clone.checkout_tree(previous_commit)
                        # Creates ref to avoid "failed to identify reference"
                        repo_clone.create_tag(str(uuid.uuid4()), previous_commit.oid, pygit2.GIT_OBJ_COMMIT, previous_commit.author, previous_commit.message)
                        repo_clone.set_head(previous_commit.oid)
                        try:
                            repo_clone.apply(pygit2.Diff.parse_diff(str(test_patch)))
                        except pygit2.GitError:
                            # Invalid patches
                            continue
                        test_actions.save_workflows()
                        pre_failed_tests = test_actions.get_failed_tests(workflow)
                        if pre_failed_tests is None:
                            # Timeout: The other commits will take similar amount of time FIXME
                            # Job failed without tests failing
                            test_actions.delete_workflows()
                            logging.info(f"Skipping commit {commit.hex}: failed previous tests")
                            continue
                        test_actions.delete_workflows()

                        repo_clone.checkout_tree(commit)
                        # Creates ref to avoid "failed to identify reference"
                        repo_clone.create_tag(str(uuid.uuid4()), commit.oid, pygit2.GIT_OBJ_COMMIT, commit.author, commit.message)
                        repo_clone.set_head(commit.oid)
                        test_actions.save_workflows()

                        cur_failed_tests = test_actions.get_failed_tests(workflow)
                        if cur_failed_tests is None:
                            # Timeout: The other commits will take similar amount of time FIXME
                            # Job failed without tests failing
                            test_actions.delete_workflows()
                            logging.info(f"Skipping commit {commit.hex}: failed current tests")
                            continue
                        test_actions.delete_workflows()
                        
                        previous_failed_tests.extend(pre_failed_tests)
                        current_failed_tests.extend(cur_failed_tests)
                        workflow_succeeded = True

                    # Back to default branch (avoids conflitcts)
                    repo_clone.reset(first_commit.oid, pygit2.GIT_RESET_HARD)
                    failed_diff = list(set(x.classname + "#" + x.name for x in previous_failed_tests)
                                       .difference(set(x.classname + "#" + x.name for x in current_failed_tests)))

                    # No tests were fixed FIXME: check the if the tests in the commit were the ones with diff
                    if len(failed_diff) == 0 or not workflow_succeeded:
                        logging.info(f"Skipping commit {commit.hex}: no failed diff")
                        continue

                    fp.write((json.dumps(data) + "\n"))
        
        # test_actions.remove_containers()
        shutil.rmtree(repo_path)


class RepoCrawler:
    __GITHUB_CREATION_DATE = "2008-02-08"
    __PAGE_SIZE = 100

    def __init__(self, query: str, rate_limiter: RateLimiter, pagination_freq: str=None, n_workers: int = 1):
        '''
        Args:
            query (str): String with the Github searching format
                https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories
            pagination_freq (str): Useful if the number of repos to get is superior to 1000 results (Github limit).
                If the value is 'D', each request will be limited to the repos created in a single day, until all the days 
                are obtained.
                The possible values are listed here:
                https://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html#timeseries-offset-aliases
        '''
        self.github: Github = Github(
            login_or_token=os.environ["GITHUB_ACCESS_TOKEN"], 
            per_page=RepoCrawler.__PAGE_SIZE, 
        )
        self.query: str = query
        self.pagination_freq: str = pagination_freq
        self.requests: int = 0
        self.rate_lim = rate_limiter
        self.n_workers = n_workers
        self.executor = ThreadPoolExecutor(max_workers=self.n_workers)
        self.futures = []

    def __get_creation_range(self):
        created = list(filter(lambda x: x.startswith('created:'), self.query.split(' ')))
        start_date = datetime.fromisoformat(RepoCrawler.__GITHUB_CREATION_DATE)
        end_date = datetime.today()
        if len(created) != 0:
            created = created[0][8:]
        else:
            created = None

        if created is None:
            pass
        elif created.startswith('>='):
            start_date = datetime.fromisoformat(created[2:])
        elif created.startswith('>'):
            start_date = datetime.fromisoformat(created[1:])

            if len(created[1:]) == 10:
                # Next day since hour is not specified
                start_date = start_date.replace(hour=23, minute=59, second=59) + timedelta(seconds=1)
            else:
                start_date = start_date + timedelta(seconds=1)
        elif created.startswith('<='):
            end_date = datetime.fromisoformat(created[2:])
            # End of day when hour is not specified
            if len(ed) == 10:
                end_date = end_date.replace(hour=23, minute=59, second=59)
        elif created.startswith('<'):
            end_date = datetime.fromisoformat(created[1:]) - timedelta(seconds=1)
        elif '..' in created:
            sd, ed = created.split('..')
            if sd != '*':
                start_date = datetime.fromisoformat(sd)
            if ed != '*':
                end_date = datetime.fromisoformat(ed)
                # End of day when hour is not specified
                if len(ed) == 10:
                    end_date = end_date.replace(hour=23, minute=59, second=59)
        
        return (start_date.isoformat(), end_date.isoformat())


    def __search_repos(self, query: str, repo_strategy: RepoStrategy):
        logging.info(f'Searching repos with query: {query}')
        page_list = self.rate_lim.request(self.github.search_repositories, query)
        totalCount = self.rate_lim.request(getattr, page_list, 'totalCount')

        if (totalCount == 1000):
            logging.warning(f'1000 results limit of the GitHub API was reached.\nQuery: {query}')
        n_pages = math.ceil(totalCount / RepoCrawler.__PAGE_SIZE)
        for p in range(n_pages):
            repos = self.rate_lim.request(page_list.get_page, p)
            results = []
            for repo in repos:
                args = (repo, )
                self.futures.append(self.executor.submit(repo_strategy.handle_repo, *args))


    def get_repos(self, repo_strategy: RepoStrategy):
        if self.pagination_freq is not None:
            creation_range = self.__get_creation_range()
            date_ranges = pd.date_range(
                start=creation_range[0], 
                end=creation_range[1], 
                freq=self.pagination_freq,
                inclusive="neither")

            query = list(filter(lambda x: not x.startswith('created:'), self.query.split(' ')))
            query = ' '.join(query)
            start_date = creation_range[0]

            for i in range(len(date_ranges)):
                end_date = date_ranges[i] - timedelta(seconds=1)
                created_filter = f" created:{start_date}..{end_date.strftime('%Y-%m-%dT%H:%M:%S')}"
                self.__search_repos(query + created_filter, repo_strategy)
                start_date = date_ranges[i].strftime('%Y-%m-%dT%H:%M:%S')
                           
            end_date = creation_range[1]
            created_filter = f" created:{start_date}..{end_date}"
            self.__search_repos(query + created_filter, repo_strategy)
            
            for future in tqdm.tqdm(as_completed(self.futures)):
                future.result()
        else:
            return self.__search_repos(query, repo_strategy)
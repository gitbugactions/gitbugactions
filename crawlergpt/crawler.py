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
import threading
import pandas as pd
from unidiff import PatchSet
from abc import ABC, abstractmethod
from crawlergpt.actions.actions import GitHubActions
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
        self.lock = threading.Lock()

    def request(self, fn, *args, **kwargs):
        self.lock.acquire()
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
        self.lock.release()

        try:
            return fn(*args, **kwargs)
        except RateLimitExceededException as exc:
            self.lock.acquire()
            logging.warning(f"Github Rate Limit Exceeded: {exc.headers}")
            reset_time = datetime.fromtimestamp(int(exc.headers["x-ratelimit-reset"]))
            retry_after = (reset_time - datetime.now()).total_seconds() + 1
            retry_after = max(retry_after, 0)  # In case we hit a negative total_seconds
            time.sleep(retry_after)
            retries -= 1
            self.lock.release()
            if retries == 0:
                raise exc


class RepoStrategy(ABC):
    def __init__(self, data_path: str):
        self.data_path = data_path

    @abstractmethod
    def handle_repo(self, repo: Repository):
        pass


# FIXME identify build tool
class BugCollectorStrategy(RepoStrategy):
    def __init__(self, data_path: str, rate_limiter: RateLimiter):
        super().__init__(data_path)
        self.rate_lim = rate_limiter

    def handle_repo(self, repo: Repository):
        self.__HandleRepo(repo, self.data_path).handle_repo()

    # The helper class is required because: 
    # 1. The strategy must be passed instantiated to the Crawler
    # 2. The handle_repo method should be parallelizable
    class __HandleRepo:
        __FIX_ISSUE_REGEX = "(close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved) #([0-9]*)"

        def __init__(self, repo: Repository, data_path: str):
            self.repo = repo
            self.data_path = data_path
            self.repo_path = os.path.join(tempfile.gettempdir(), self.repo.full_name.replace('/', '-'))
            if os.path.exists(self.repo_path):
                shutil.rmtree(self.repo_path)
            logging.info(f"Cloning {self.repo.full_name} - {self.repo.clone_url}")
            self.repo_clone = pygit2.clone_repository(
                self.repo.clone_url, 
                self.repo_path
            )
            self.default_actions = GitHubActions(self.repo_path)
            self.__get_default_actions()

        def __get_default_actions(self):
            if len(list(self.repo_clone.references.iterator())) == 0:
                return
            first_commit = None

            for commit in self.repo_clone.walk(self.repo_clone.head.target):
                if first_commit is None:
                    first_commit = commit
                self.repo_clone.checkout_tree(commit)
                self.repo_clone.set_head(commit.oid)
                actions = GitHubActions(self.repo_path)
                if len(actions.test_workflows) > 0:
                    self.default_actions = actions

            self.repo_clone.reset(first_commit.oid, pygit2.GIT_RESET_HARD)
            
        def __is_bug_fix(self, commit):
            return 'fix' in commit.message.lower()
        
        def __get_patches(self, repo_clone, commit, previous_commit):
            diff = repo_clone.diff(previous_commit.hex, commit.hex)
            patch = PatchSet(diff.patch)
            bug_patch = PatchSet('')
            test_patch = PatchSet('')

            for p in patch:
                # FIXME change keywords according to build tool
                if any([keyword in p.source_file.split(os.sep) for keyword in ['test', 'tests']]):
                    test_patch.append(p)
                else:
                    bug_patch.append(p)

            return bug_patch, test_patch
        
        def __run_tests(self):
            res = []
            workflow_succeeded = False

            test_actions = GitHubActions(self.repo_clone.workdir)
            if len(test_actions.test_workflows) == 0:
                test_actions = self.default_actions
            test_actions.save_workflows()

            for workflow in test_actions.test_workflows:
                failed_tests, _, _ = test_actions.run_workflow(workflow)
                if failed_tests is None:
                    # Timeout: The other commits will take similar amount of time FIXME
                    # Job failed without tests failing
                    logging.info(f"{self.repo.full_name}: failed current tests")
                    continue
                
                res.extend(failed_tests)
                workflow_succeeded = True
            test_actions.delete_workflows()

            return res, workflow_succeeded

        def __get_diff_tests(self, commit, previous_commit, test_patch):
            previous_failed_tests = []
            current_failed_tests = []
            pre_workflow_succeeded = False
            cur_workflow_succeeded = False

            # Apply diff and run tests
            self.repo_clone.checkout_tree(previous_commit)
            # Creates ref to avoid "failed to identify reference"
            self.repo_clone.create_tag(str(uuid.uuid4()), previous_commit.oid, pygit2.GIT_OBJ_COMMIT, previous_commit.author, previous_commit.message)
            self.repo_clone.set_head(previous_commit.oid)
            try:
                self.repo_clone.apply(pygit2.Diff.parse_diff(str(test_patch)))
            except pygit2.GitError:
                # Invalid patches
                return current_failed_tests, previous_failed_tests, False
            previous_failed_tests, pre_workflow_succeeded = self.__run_tests()

            self.repo_clone.checkout_tree(commit)
            # Creates ref to avoid "failed to identify reference"
            self.repo_clone.create_tag(str(uuid.uuid4()), commit.oid, pygit2.GIT_OBJ_COMMIT, \
                                  commit.author, commit.message)
            self.repo_clone.set_head(commit.oid)
            current_failed_tests, cur_workflow_succeeded = self.__run_tests()

            workflow_succeeded = pre_workflow_succeeded and cur_workflow_succeeded
            return current_failed_tests, previous_failed_tests, workflow_succeeded
        
        def handle_repo(self):
            if len(list(self.repo_clone.references.iterator())) == 0:
                return

            with open(self.data_path, "w") as fp:
                first_commit = None

                for commit in self.repo_clone.walk(self.repo_clone.head.target):
                    if first_commit is None:
                        first_commit = commit

                    if not self.__is_bug_fix(commit):
                        continue

                    try:
                        previous_commit = self.repo_clone.revparse_single(commit.hex + '~1')
                    except KeyError:
                        # The current commit is the first one
                        continue

                    data = { 
                        'repository': self.repo.full_name,
                        'clone_url': self.repo.clone_url,
                        'timestamp': datetime.utcnow().isoformat() + "Z",
                        'commit_hash': commit.hex,
                        'commit_message': commit.message,
                        'related_issues': '',
                    }

                    bug_patch, test_patch = self.__get_patches(self.repo_clone, commit, previous_commit)
                    # Ignore commits without tests
                    # FIXME check if test_patch only has deletes
                    if len(test_patch) == 0 or len(bug_patch) == 0:
                        logging.info(f"Skipping commit {self.repo.full_name} {commit.hex}: no test/bug patch")
                        continue

                    data['bug_patch'] = str(bug_patch)
                    data['test_patch'] = str(test_patch)

                    current_failed_tests, previous_failed_tests, workflow_succeeded = \
                            self.__get_diff_tests(commit, previous_commit, test_patch)

                    # Back to default branch (avoids conflitcts)
                    self.repo_clone.reset(first_commit.oid, pygit2.GIT_RESET_HARD)
                    failed_diff = list(set(x.classname + "#" + x.name for x in previous_failed_tests)
                                        .difference(set(x.classname + "#" + x.name for x in current_failed_tests)))

                    # FIXME check only if the current commit passed
                    # Check the tests that failed in the previous commit
                    # Save the tests that failed
                    if len(failed_diff) == 0 or not workflow_succeeded:
                        logging.info(f"Skipping commit {self.repo.full_name} {commit.hex}: no failed diff")
                        continue

                    fp.write((json.dumps(data) + "\n"))
            
            shutil.rmtree(self.repo_path)


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
            if len(created[2:]) == 10:
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
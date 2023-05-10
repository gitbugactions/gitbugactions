import os
import re
import json
import time
import math
import shutil
import pygit2
import tempfile
import logging
import pandas as pd
from abc import ABC, abstractmethod
from github import Github, Repository
from datetime import datetime, timedelta

# FIXME change to custom logger
logging.basicConfig(level=logging.INFO)

class RepoStrategy(ABC):
    def __init__(self, data_path: str):
        self.data_path = data_path

    @abstractmethod
    def handle_repo(self, repo: Repository):
        pass


class BugCollectorStrategy(RepoStrategy):
    __FIX_ISSUE_REGEX = "(close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved) #([0-9]*)"

    def __init__(self, data_path: str):
        super().__init__(data_path)

    def handle_repo(self, repo: Repository):
        logging.info(f"Cloning {repo.full_name} - {repo.clone_url}")
        repo_path = os.path.join(tempfile.gettempdir(), repo.name)
        repo_clone = pygit2.clone_repository(
            repo.clone_url, 
            repo_path
        )

        if len(list(repo_clone.references.iterator())) > 0:
            with open(self.data_path, "ab") as fp:
                for commit in repo_clone.walk(repo_clone.head.target):
                    issues = re.findall(BugCollectorStrategy.__FIX_ISSUE_REGEX, commit.message)
                    if len(issues) > 0:
                        data = { 
                            'repository': repo.full_name,
                            'clone_url': repo.clone_url,
                            'timestamp': datetime.utcnow().isoformat() + "Z",
                            'commit_hash': commit.hex,
                            'message': commit.message 
                        }

                        for issue in issues:
                            gh_issue = repo.get_issue(number=int(issue[1]))
                            data['message'] += f"\n Issue #{issue[1]} - {gh_issue.title}\n"
                            data['message'] += gh_issue.body
                            time.sleep(1)

                        data['patch'] = repo_clone.diff(commit.hex, commit.hex + '~1').patch
                        fp.write((json.dumps(data) + "\n").encode('utf-8'))
        
        shutil.rmtree(repo_path)
        time.sleep(2) # FIXME we can remove when the process takes more time


class RepoCrawler:
    __GITHUB_CREATION_DATE = "2008-02-08"
    __PAGE_SIZE = 100

    def __init__(self, query: str, pagination_freq: str=None):
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
        self.github: Github = Github(login_or_token=os.environ["GITHUB_ACCESS_TOKEN"], per_page=RepoCrawler.__PAGE_SIZE)
        self.query: str = query
        self.pagination_freq: str = pagination_freq

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
        page_list = self.github.search_repositories(query)
        if (page_list.totalCount == 1000):
            logging.warning(f'1000 results limit of the GitHub API was reached.\nQuery: {query}')
        n_pages = math.ceil(page_list.totalCount / RepoCrawler.__PAGE_SIZE)
        for p in range(n_pages):
            repos = page_list.get_page(p)
            for repo in repos:
                repo_strategy.handle_repo(repo)
            time.sleep(1.5)

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
                time.sleep(1)
            
            end_date = creation_range[1]
            created_filter = f" created:{start_date}..{end_date}"
            self.__search_repos(query + created_filter, repo_strategy)
        else:
            return self.__search_repos(query, repo_strategy)
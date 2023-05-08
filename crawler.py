import os
import time
import math
import warnings
import pandas as pd
from github import Github
from datetime import datetime, timedelta

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
            # Next day
            start_date = datetime.fromisoformat(created[1:]).replace(hour=23, minute=59, second=59) + timedelta(seconds=1)
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

    def __search_repos(self, query):
        repos = []
        page_list = self.github.search_repositories(query)
        if (page_list.totalCount == 1000):
            warnings.warn(f'1000 results limit of the GitHub API was reached.\nQuery: {query}')
        n_pages = math.ceil(page_list.totalCount / RepoCrawler.__PAGE_SIZE)
        for p in range(n_pages):
            repos += page_list.get_page(p)
            time.sleep(1.5)
        return repos

    def get_repos(self):
        if self.pagination_freq is not None:
            creation_range = self.__get_creation_range()
            date_ranges = pd.date_range(
                start=creation_range[0], 
                end=creation_range[1], 
                freq=self.pagination_freq,
                inclusive="neither")
            repos = []
            
            query = list(filter(lambda x: not x.startswith('created:'), self.query.split(' ')))
            query = ' '.join(query)
            start_date = creation_range[0]

            for i in range(len(date_ranges)):
                end_date = date_ranges[i] - timedelta(seconds=1)
                created_filter = f" created:{start_date}..{end_date.strftime('%Y-%m-%dT%H:%M:%S')}"
                repos += self.__search_repos(query + created_filter)
                start_date = date_ranges[i].strftime('%Y-%m-%dT%H:%M:%S')
                time.sleep(1)
            
            end_date = creation_range[1]
            created_filter = f" created:{start_date}..{end_date}"
            repos += self.__search_repos(query + created_filter)

            return repos
        else:
            return self.github.search_repositories(self.query)
        
# Next step: clone to get info about
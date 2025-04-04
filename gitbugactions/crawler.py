import logging
import math
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Optional, Callable

import pandas as pd
import tqdm
from github import Repository

from gitbugactions.actions.actions import ActCacheDirManager
from gitbugactions.github_api import GithubAPI

# FIXME change to custom logger
logging.basicConfig(level=logging.INFO)


class RepoStrategy(ABC):
    def __init__(self, data_path: str):
        self.data_path = data_path

    @abstractmethod
    def handle_repo(self, repo: Repository):
        pass


class RepoCrawler:
    __GITHUB_CREATION_DATE = "2008-02-08"
    __PAGE_SIZE = 100

    def __init__(
        self,
        query: str,
        pagination_freq: Optional[str],
        n_workers: int = 1,
        cleanup_interval: int = 100,
        cleanup_function: Optional[Callable] = None,
    ):
        """
        Args:
            query (str): String with the Github searching format
                https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories
            pagination_freq (str): Useful if the number of repos to collect is superior to 1000 results (GitHub limit).
                If the value is 'D', each request will be limited to the repos created in a single day, until all the days
                are obtained.
                The possible values are listed here:
                https://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html#timeseries-offset-aliases
            n_workers (int): Number of worker threads for parallel processing
            cleanup_interval (int): Number of jobs after which to run the cleanup function
            cleanup_function (Callable): Function to run periodically for cleanup
        """
        self.github: GithubAPI = GithubAPI(
            per_page=RepoCrawler.__PAGE_SIZE,
        )
        self.query: str = query
        self.pagination_freq: str = pagination_freq
        self.requests: int = 0
        self.n_workers = n_workers
        self.executor = ThreadPoolExecutor(max_workers=self.n_workers)
        self.futures = []
        self.completed_jobs = 0
        self.cleanup_interval = cleanup_interval
        self.cleanup_function = cleanup_function
        # Must init several act-cache dirs for parallel processing to work
        ActCacheDirManager.init_act_cache_dirs(n_dirs=n_workers)

    def __get_creation_range(self):
        created = list(
            filter(lambda x: x.startswith("created:"), self.query.split(" "))
        )
        start_date = datetime.fromisoformat(RepoCrawler.__GITHUB_CREATION_DATE)
        end_date = datetime.today()
        if len(created) != 0:
            created = created[0][8:]
        else:
            created = None

        if created is None:
            pass
        elif created.startswith(">="):
            start_date = datetime.fromisoformat(created[2:])
        elif created.startswith(">"):
            start_date = datetime.fromisoformat(created[1:])

            if len(created[1:]) == 10:
                # Next day since hour is not specified
                start_date = start_date.replace(
                    hour=23, minute=59, second=59
                ) + timedelta(seconds=1)
            else:
                start_date = start_date + timedelta(seconds=1)
        elif created.startswith("<="):
            end_date = datetime.fromisoformat(created[2:])
            # End of day when hour is not specified
            if len(created[2:]) == 10:
                end_date = end_date.replace(hour=23, minute=59, second=59)
        elif created.startswith("<"):
            end_date = datetime.fromisoformat(created[1:]) - timedelta(seconds=1)
        elif ".." in created:
            sd, ed = created.split("..")
            if sd != "*":
                start_date = datetime.fromisoformat(sd)
            if ed != "*":
                end_date = datetime.fromisoformat(ed)
                # End of day when hour is not specified
                if len(ed) == 10:
                    end_date = end_date.replace(hour=23, minute=59, second=59)

        return (start_date.isoformat(), end_date.isoformat())

    def __wait_for_completion(self):
        """Wait for all current futures to complete"""
        for future in tqdm.tqdm(as_completed(self.futures)):
            future.result()
            self.completed_jobs += 1
        self.futures = []

    def __run_cleanup_if_needed(self):
        """Check if cleanup is needed and run it if necessary"""
        if (
            self.cleanup_function is not None
            and len(self.futures) > 0
            and len(self.futures) % self.cleanup_interval == 0
        ):
            logging.info(
                f"Running cleanup function after {self.completed_jobs} submitted jobs"
            )
            # Wait for all current jobs to complete before running cleanup
            self.__wait_for_completion()
            # Run the cleanup function
            self.cleanup_function()
            logging.info("Cleanup completed, resuming repository collection")

    def __search_repos(self, query: str, repo_strategy: RepoStrategy):
        logging.info(f"Searching repos with query: {query}")
        page_list = self.github.search_repositories(query)
        totalCount = self.github.token.search_rate_limiter.request(
            getattr, page_list, "totalCount"
        )
        if totalCount is None:
            logging.error(f'Search "{query}" failed')
            return
        elif totalCount == 1000:
            logging.warning(
                f"1000 results limit of the GitHub API was reached.\nQuery: {query}"
            )
        n_pages = math.ceil(totalCount / RepoCrawler.__PAGE_SIZE)
        for p in range(n_pages):
            repos = self.github.token.search_rate_limiter.request(page_list.get_page, p)
            results = []
            for repo in repos:
                args = (repo,)
                self.futures.append(
                    self.executor.submit(repo_strategy.handle_repo, *args)
                )
                # Check if we need to run cleanup after adding this job
                self.__run_cleanup_if_needed()

    def get_repos(self, repo_strategy: RepoStrategy):
        if self.pagination_freq is not None:
            creation_range = self.__get_creation_range()
            date_ranges = pd.date_range(
                start=creation_range[0],
                end=creation_range[1],
                freq=self.pagination_freq,
                inclusive="neither",
            )

            query = list(
                filter(lambda x: not x.startswith("created:"), self.query.split(" "))
            )
            query = " ".join(query)
            start_date = creation_range[0]

            for i in range(len(date_ranges)):
                end_date = date_ranges[i] - timedelta(seconds=1)
                created_filter = (
                    f" created:{start_date}..{end_date.strftime('%Y-%m-%dT%H:%M:%S')}"
                )
                self.__search_repos(query + created_filter, repo_strategy)
                start_date = date_ranges[i].strftime("%Y-%m-%dT%H:%M:%S")

            end_date = creation_range[1]
            created_filter = f" created:{start_date}..{end_date}"
            self.__search_repos(query + created_filter, repo_strategy)

            # Wait for all remaining futures to complete
            self.__wait_for_completion()
        else:
            self.__search_repos(self.query, repo_strategy)
            # Wait for all remaining futures to complete
            self.__wait_for_completion()

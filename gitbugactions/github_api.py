import os
import time
import threading
import logging

from typing import List
from github import Github, RateLimitExceededException
from datetime import datetime
from functools import partial


class RateLimiter:
    """
    Rate Limiter for the Github API
    """

    def __init__(self, requests_limit: int, reset_seconds: int):
        self.requests = 0
        self.requests_limit = requests_limit
        self.reset_seconds = reset_seconds
        self.first_request = datetime.now()
        self.lock = threading.Lock()

    def request(self, fn, *args, **kwargs):
        with self.lock:
            time_after_reset = (datetime.now() - self.first_request).total_seconds()
            retries = 3
            if self.requests == 0:
                self.first_request = datetime.now()
            elif time_after_reset > self.reset_seconds:
                self.requests = 0
                self.first_request = datetime.now()
            if self.requests == self.requests_limit:
                time.sleep(self.reset_seconds - time_after_reset)
                self.requests = 0
            self.requests += 1

        while retries > 0:
            try:
                return fn(*args, **kwargs)
            except RateLimitExceededException as exc:
                with self.lock:
                    logging.warning(f"Github Rate Limit Exceeded: {exc.headers}")
                    reset_time = datetime.fromtimestamp(
                        int(exc.headers["x-ratelimit-reset"])
                    )
                    retry_after = (reset_time - datetime.now()).total_seconds() + 1
                    retry_after = max(
                        retry_after, 0
                    )  # In case we hit a negative total_seconds
                    time.sleep(retry_after)
                    retries -= 1
                if retries == 0:
                    raise exc

    def update_requests(self, requests: int):
        with self.lock:
            self.requests = requests


class SearchRateLimiter(RateLimiter):
    """
    Rate Limiter for the Github search API. The search API has different rate limits
    than the core API.
    """

    def __init__(self):
        super().__init__(
            # The real limit is 30, but we try to avoid it
            requests_limit=29,
            reset_seconds=60,
        )


class CoreRateLimiter(RateLimiter):
    """
    Rate Limiter for the Github core API.
    """

    def __init__(self):
        super().__init__(
            # The real limit is 5000, but we try to avoid it
            requests_limit=4995,
            reset_seconds=3600,
        )


class GithubToken:
    __TOKENS: List["GithubToken"] = None
    __TOKENS_LOCK: threading.Lock = threading.Lock()
    __CURRENT_TOKEN = 0
    __OFFSET = 200
    __UPDATE_RATE_INTERVAL = 5  # in seconds

    def __init__(self, token: str):
        self.lock_rate: threading.Lock = threading.Lock()
        self.last_update: float = 0
        self.token: str = token
        self.search_rate_limiter = SearchRateLimiter()
        self.core_rate_limiter = CoreRateLimiter()
        GithubToken.__TOKENS.append(self)
        self.github = GithubAPI(token=self)

    def update_rate_limit(self):
        with self.lock_rate:
            if time.time() - self.last_update > GithubToken.__UPDATE_RATE_INTERVAL:
                rate_limit = self.github.get_rate_limit()
                self.search_rate_limiter.update_requests(
                    rate_limit.search.limit - rate_limit.search.remaining
                )
                self.core_rate_limiter.update_requests(
                    rate_limit.core.limit - rate_limit.core.remaining
                )

    @staticmethod
    def has_tokens() -> bool:
        return "GITHUB_ACCESS_TOKEN" in os.environ

    @staticmethod
    def init_tokens():
        if GithubToken.has_tokens():
            GithubToken.__TOKENS = []
            tokens = os.environ["GITHUB_ACCESS_TOKEN"].split(",")
            for token in tokens:
                GithubToken(token)
        else:
            logging.error("No environment variable GITHUB_ACCESS_TOKEN provided.")
            exit(1)

    @staticmethod
    def __wait_for_tokens():
        if len(GithubToken.__TOKENS) == 0:
            return

        soonest_reset = GithubToken.__TOKENS[0].github.get_rate_limit().core.reset
        for token in GithubToken.__TOKENS[1:]:
            reset = token.github.get_rate_limit().core.reset
            if reset < soonest_reset:
                soonest_reset = reset
        time.sleep((datetime.now() - soonest_reset).total_seconds())

    @staticmethod
    def get_token() -> "GithubToken":
        with GithubToken.__TOKENS_LOCK:
            if GithubToken.__TOKENS is None:
                GithubToken.init_tokens()

            len_tokens = (
                0 if not GithubToken.has_tokens() else len(GithubToken.__TOKENS)
            )
            if len_tokens == 0:
                return None

            next_tokens = (
                GithubToken.__TOKENS[GithubToken.__CURRENT_TOKEN :]
                + GithubToken.__TOKENS[: GithubToken.__CURRENT_TOKEN]
            )
            for token in next_tokens:
                GithubToken.__CURRENT_TOKEN = (
                    GithubToken.__CURRENT_TOKEN + 1
                ) % len_tokens
                if (
                    token.core_rate_limiter.requests_limit
                    - token.core_rate_limiter.requests
                    >= GithubToken.__OFFSET
                ):
                    return token

            GithubToken.__wait_for_tokens()


class GithubAPI(Github):
    def __init__(self, *args, token: GithubToken = None, **kwargs):
        if "login_or_token" not in kwargs:
            self.token = GithubToken.get_token() if token is None else token
            if self.token is not None:
                kwargs["login_or_token"] = self.token.token
        else:
            super().__init__(*args, **kwargs)
            return

        super().__init__(*args, **kwargs)
        for attr, val in Github.__dict__.items():
            if attr.startswith("_") or not callable(val):
                continue

            if attr.startswith("search"):
                setattr(
                    self,
                    attr,
                    partial(self.token.search_rate_limiter.request, partial(val, self)),
                )
            else:
                setattr(
                    self,
                    attr,
                    partial(self.token.core_rate_limiter.request, partial(val, self)),
                )

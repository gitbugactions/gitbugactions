import os, sys
import time
import logging
from datetime import datetime
from github import Github
from typing import List


class GithubToken:
    __TOKENS: List["GithubToken"] = None
    __CURRENT_TOKEN = 0
    __OFFSET = 200

    def __init__(self, token):
        self.token = token
        self.github = Github(login_or_token=token)
        self.update_rate_limit()
        GithubToken.__TOKENS.append(self)

    def update_rate_limit(self):
        self.remaining = self.github.get_rate_limit().core.remaining

    @staticmethod
    def has_tokens():
        return "GITHUB_ACCESS_TOKEN" in os.environ

    @staticmethod
    def init_tokens():
        if GithubToken.has_tokens():
            GithubToken.__TOKENS = []
            tokens = os.environ["GITHUB_ACCESS_TOKEN"].split(",")
            for token in tokens:
                GithubToken(token)
        else:
            print("No GITHUB_ACCESS_TOKEN provided.")
            sys.stdout.flush()
            sys.stderr.flush()


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
        if GithubToken.__TOKENS is None:
            GithubToken.init_tokens()

        len_tokens = 0 if not GithubToken.has_tokens() else len(GithubToken.__TOKENS)
        if len_tokens == 0:
            return None

        next_tokens = (
            GithubToken.__TOKENS[GithubToken.__CURRENT_TOKEN :]
            + GithubToken.__TOKENS[: GithubToken.__CURRENT_TOKEN]
        )
        for token in next_tokens:
            GithubToken.__CURRENT_TOKEN = (GithubToken.__CURRENT_TOKEN + 1) % len_tokens
            if token.remaining >= GithubToken.__OFFSET:
                return token

        GithubToken.__wait_for_tokens()

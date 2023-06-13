import os
import logging
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
            tokens = os.environ["GITHUB_ACCESS_TOKEN"].split(',')
            for token in tokens:
                GithubToken(token)
        else:
            logging.warning("No GITHUB_ACCESS_TOKEN provided.")

    @staticmethod
    def get_token() -> "GithubToken":
        if GithubToken.__TOKENS is None:
            GithubToken.init_tokens()

        len_tokens = 0 if not GithubToken.has_tokens() else len(GithubToken.__TOKENS)
        if len_tokens == 0:
            return None
        
        next_tokens = GithubToken.__TOKENS[GithubToken.__CURRENT_TOKEN:] + \
            GithubToken.__TOKENS[:GithubToken.__CURRENT_TOKEN]
        for token in next_tokens:
            GithubToken.__CURRENT_TOKEN = (GithubToken.__CURRENT_TOKEN + 1) % len_tokens
            if token.remaining >= GithubToken.__OFFSET:
                return token
            
        raise RuntimeError("No tokens available.")
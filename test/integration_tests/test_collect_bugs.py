from gitbugactions.github_api import GithubToken


class TestCollectBugs:
    TOKEN_USAGE: int = 0

    @classmethod
    def setup_class(cls):
        GithubToken.init_tokens()
        cls.TOKEN_USAGE = cls.get_token_usage()

    @staticmethod
    def get_token_usage():
        token_usage = 0
        if GithubToken.has_tokens():
            for token in GithubToken._GithubToken__TOKENS:
                token_usage += token.core_rate_limiter.requests
            return token_usage
        return token_usage

    @staticmethod
    def get_test_results(tests):
        passed, failure = 0, 0
        for test in tests:
            if test["results"][0]["result"] == "Passed":
                passed += 1
            elif test["results"][0]["result"] == "Failure":
                failure += 1
        return passed, failure

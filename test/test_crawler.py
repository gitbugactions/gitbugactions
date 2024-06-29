import time
import pytest

from unittest import mock
from concurrent.futures import ThreadPoolExecutor
from gitbugactions.github_api import SearchRateLimiter, CoreRateLimiter, GithubAPI


def test_rate_limiter():
    rate_limiters = [CoreRateLimiter(), SearchRateLimiter()]
    for rate_limiter in rate_limiters:
        executor = ThreadPoolExecutor(max_workers=2)
        rate_limiter.lock.acquire()
        assert rate_limiter.lock.locked()
        executor.submit(rate_limiter.request, (lambda x: x + 1, 2))
        executor.submit(rate_limiter.request, (lambda x: x + 1, 2))
        time.sleep(1)
        assert rate_limiter.requests == 0
        rate_limiter.lock.release()
        time.sleep(1)
        assert rate_limiter.requests == 2


@pytest.mark.first
def test_github_api():
    with mock.patch("github.Github.get_emojis") as get_emojis:
        github = GithubAPI()
        github.get_emojis()
        github.get_emojis()
        assert get_emojis.call_count == 2
        assert github.token.core_rate_limiter.requests == 2

    with mock.patch("github.Github.search_repositories") as search_repositories:
        github = GithubAPI()
        github.search_repositories("test")
        github.search_repositories("test")
        assert search_repositories.call_count == 2
        assert github.token.search_rate_limiter.requests == 2

import time
from concurrent.futures import ThreadPoolExecutor
from crawlergpt.crawler import RateLimiter

def test_ratelimiter():
    rate_limiter = RateLimiter()
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


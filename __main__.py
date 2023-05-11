from crawler import RepoCrawler, BugCollectorStrategy, RateLimiter

if __name__ == '__main__':
    query = input()
    rate_limiter = RateLimiter()
    crawler = RepoCrawler(query, rate_limiter, pagination_freq='D')
    crawler.get_repos(BugCollectorStrategy("out.jsonl", rate_limiter))
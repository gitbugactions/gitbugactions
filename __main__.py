from crawler import RepoCrawler, BugCollectorStrategy

if __name__ == '__main__':
    query = input()
    crawler = RepoCrawler(query, pagination_freq='D')
    crawler.get_repos(BugCollectorStrategy("out.jsonl"))
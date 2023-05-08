from crawler import RepoCrawler

if __name__ == '__main__':
    query = input()
    crawler = RepoCrawler(query, pagination_freq='D')
    print(len(crawler.get_repos()))
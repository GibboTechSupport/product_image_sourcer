from icrawler.builtin import BingImageCrawler
import logging

class MyBingCrawler(BingImageCrawler):
    def process_meta(self, task):
        print(f"DEBUG: Found {task}")
        # task usually contains 'file_url', etc.
        # I want to see if 'title' or description is available.
        return super().process_meta(task)

crawler = MyBingCrawler(storage={'root_dir': 'test_icrawler'})
crawler.crawl(keyword='Nike shoes', max_num=1)

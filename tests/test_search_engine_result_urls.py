import unittest

from core.search.engine import SearchEngine, SearchEngineClient


class SearchEngineResultURLTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = SearchEngineClient.__new__(SearchEngineClient)

    def test_baidu_relative_result_url_is_normalized(self) -> None:
        normalized = self.client._normalize_result_url("/s?wd=example", SearchEngine.BAIDU)
        self.assertEqual("https://www.baidu.com/s?wd=example", normalized)

    def test_malformed_http_url_without_host_is_repaired(self) -> None:
        normalized = self.client._normalize_result_url("https:///s?wd=example", SearchEngine.BAIDU)
        self.assertEqual("https://www.baidu.com/s?wd=example", normalized)

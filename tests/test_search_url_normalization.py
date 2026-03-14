import unittest

from core.search.advanced import AdvancedSearchEngine, AdvancedSearchEngineClient


class SearchUrlNormalizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = AdvancedSearchEngineClient.__new__(AdvancedSearchEngineClient)

    def test_malformed_scheme_without_host_is_repaired(self) -> None:
        normalized = self.client._normalize_result_url(
            "https:///s?wd=example",
            AdvancedSearchEngine.BAIDU,
        )
        self.assertEqual("https://www.baidu.com/s?wd=example", normalized)

    def test_relative_path_is_joined_with_engine_base(self) -> None:
        normalized = self.client._normalize_result_url(
            "/search?q=test",
            AdvancedSearchEngine.GOOGLE,
        )
        self.assertEqual("https://www.google.com/search?q=test", normalized)

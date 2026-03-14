import unittest

from core.element_storage import ElementFeature
try:
    from core.parser import AdaptiveParser
except ModuleNotFoundError:
    AdaptiveParser = None  # type: ignore[assignment]


def _feature(selector: str) -> ElementFeature:
    return ElementFeature(
        url="https://example.com",
        selector=selector,
        tag_name="div",
        text_content=selector,
    )


@unittest.skipIf(AdaptiveParser is None, "bs4 dependency is unavailable")
class AdaptiveParserCacheBudgetTests(unittest.TestCase):
    def test_feature_cache_eviction_keeps_latest(self) -> None:
        parser = AdaptiveParser(use_db=False, feature_cache_max_entries=2)

        parser._cache_put("s1", _feature("s1"))
        parser._cache_put("s2", _feature("s2"))
        parser._cache_put("s3", _feature("s3"))

        self.assertEqual(list(parser._feature_cache.keys()), ["s2", "s3"])
        self.assertNotIn("s1", parser._feature_cache)

    def test_cache_get_refreshes_lru_order(self) -> None:
        parser = AdaptiveParser(use_db=False, feature_cache_max_entries=2)

        parser._cache_put("s1", _feature("s1"))
        parser._cache_put("s2", _feature("s2"))
        parser._cache_get("s1")
        parser._cache_put("s3", _feature("s3"))

        self.assertEqual(list(parser._feature_cache.keys()), ["s1", "s3"])
        self.assertNotIn("s2", parser._feature_cache)


if __name__ == "__main__":
    unittest.main()

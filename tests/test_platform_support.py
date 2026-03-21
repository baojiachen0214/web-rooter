import unittest

from core.search.advanced import AdvancedSearchEngine, AdvancedSearchEngineClient, SearchResult
from core.search.engine_config import ConfigLoader


class _FakeCrawler:
    def __init__(self) -> None:
        self.urls: list[str] = []

    async def fetch_with_retry(self, url: str, retries: int = 2):
        self.urls.append(url)
        return type(
            "FakeCrawlResult",
            (),
            {
                "success": True,
                "html": "<html></html>",
                "error": None,
                "status_code": 200,
            },
        )()


class PlatformSupportTests(unittest.IsolatedAsyncioTestCase):
    async def test_bilibili_search_uses_first_page_entrypoint(self) -> None:
        client = AdvancedSearchEngineClient.__new__(AdvancedSearchEngineClient)
        client._crawler = _FakeCrawler()
        client._browser_manager = None
        client._parse_results = lambda engine, html: [
            SearchResult(
                title="demo",
                url="https://www.bilibili.com/video/BV1xx411c7mD",
                snippet="demo",
                engine=engine.value,
                rank=1,
            )
        ]

        response = await AdvancedSearchEngineClient.search(
            client,
            AdvancedSearchEngine.BILIBILI,
            "switch 2",
            num_results=10,
        )

        self.assertIsNone(response.error)
        self.assertEqual(1, response.total_results)
        self.assertEqual(
            "https://search.bilibili.com/all?keyword=switch+2",
            client._crawler.urls[0],
        )
        self.assertNotIn("page=10", client._crawler.urls[0])

    def test_config_loader_supports_bilibili_and_xiaohongshu(self) -> None:
        loader = ConfigLoader.get_instance()
        loader.load_configs(force=True)

        self.assertTrue(loader.is_engine_supported("bilibili"))
        self.assertTrue(loader.is_engine_supported("xiaohongshu"))

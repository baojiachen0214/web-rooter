import asyncio
import sys
import types
import unittest

from config import CrawlerConfig

if "aiohttp" not in sys.modules:
    aiohttp_stub = types.ModuleType("aiohttp")

    class _DummyClientError(Exception):
        pass

    class _DummyClientTimeout:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class _DummyCookieJar:
        pass

    class _DummyConnector:
        async def close(self):
            return None

    class _DummyClientSession:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def close(self):
            return None

    aiohttp_stub.ClientError = _DummyClientError
    aiohttp_stub.ClientTimeout = _DummyClientTimeout
    aiohttp_stub.CookieJar = _DummyCookieJar
    aiohttp_stub.ClientSession = _DummyClientSession
    aiohttp_stub.ClientResponse = object
    aiohttp_stub.TCPConnector = _DummyConnector
    aiohttp_stub.BaseConnector = _DummyConnector
    sys.modules["aiohttp"] = aiohttp_stub

from core.crawler import Crawler


class _FakeContent:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    async def iter_chunked(self, _size):
        for chunk in self._chunks:
            yield chunk


class _FakeResponse:
    def __init__(self, chunks):
        self.url = "https://example.com"
        self.status = 200
        self.headers = {"Content-Type": "text/html; charset=utf-8"}
        self.cookies = {}
        self.charset = "utf-8"
        self.content = _FakeContent(chunks)
        self.closed = False

    def close(self):
        self.closed = True


class CrawlerResponseLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_process_response_truncates_oversized_bodies(self) -> None:
        crawler = Crawler(
            config=CrawlerConfig(
                MAX_IN_MEMORY_RESPONSE_BYTES=8,
                MAX_FILE_SIZE=64,
            ),
            use_cache=False,
            use_connection_pool=False,
        )
        response = _FakeResponse([b"hello", b"world", b"!"])

        result = await crawler._process_response(
            response,
            "https://example.com",
            start_time=asyncio.get_event_loop().time(),
        )

        self.assertEqual(result.html, "hellowor")
        self.assertTrue(result.metadata["body_truncated"])
        self.assertEqual(result.metadata["body_bytes"], 8)
        self.assertTrue(response.closed)

        await crawler.close()

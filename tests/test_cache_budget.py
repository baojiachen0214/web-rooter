import unittest

from core.cache import RequestCache


class RequestCacheBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_large_body_skips_in_memory_cache(self) -> None:
        cache = RequestCache(
            use_memory=True,
            use_sqlite=False,
            memory_max_size=8,
            memory_max_bytes=128,
            memory_max_body_bytes=8,
        )

        await cache.set(
            "https://example.com/large",
            b"0123456789",
            200,
            {"Content-Type": "text/html"},
        )

        stats = cache.get_stats()
        self.assertEqual(stats["requests_cached"], 0)
        self.assertEqual(stats["skipped_too_large"], 1)
        self.assertEqual(stats["memory_cache"]["size"], 0)

    async def test_memory_cache_evicts_by_byte_budget(self) -> None:
        cache = RequestCache(
            use_memory=True,
            use_sqlite=False,
            memory_max_size=8,
            memory_max_bytes=10,
            memory_max_body_bytes=8,
        )

        await cache.set("https://example.com/a", b"123456", 200, {})
        await cache.set("https://example.com/b", b"abcdef", 200, {})

        first = await cache.get("https://example.com/a")
        second = await cache.get("https://example.com/b")
        stats = cache.get_stats()

        self.assertIsNone(first)
        self.assertIsNotNone(second)
        self.assertLessEqual(stats["memory_cache"]["current_bytes"], 10)

    async def test_unwritable_sqlite_path_degrades_to_memory_cache(self) -> None:
        cache = RequestCache(
            use_memory=True,
            use_sqlite=True,
            db_path="/dev/null/web-rooter-cache.db",
            memory_max_size=8,
            memory_max_bytes=1024,
        )

        await cache.set("https://example.com/fallback", b"ok", 200, {})
        entry = await cache.get("https://example.com/fallback")
        stats = cache.get_stats()

        self.assertIsNotNone(entry)
        self.assertIn("sqlite_cache", stats)
        self.assertTrue(stats["sqlite_cache"].get("connect_error"))

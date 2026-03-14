import unittest

from core.scheduler import DEFAULT_DUPEFILTER_MAX_ENTRIES, DEFAULT_SCHEDULER_MAX_QUEUE_SIZE

try:
    from agents.spider import SpiderConfig
except ModuleNotFoundError:  # pragma: no cover - optional runtime dependency
    SpiderConfig = None  # type: ignore[assignment]


@unittest.skipIf(SpiderConfig is None, "aiohttp dependency is unavailable")
class SpiderBudgetDefaultsTests(unittest.TestCase):
    def test_spider_config_defaults_are_bounded(self) -> None:
        config = SpiderConfig()
        self.assertEqual(config.max_queue_size, DEFAULT_SCHEDULER_MAX_QUEUE_SIZE)
        self.assertEqual(config.max_dupefilter_entries, DEFAULT_DUPEFILTER_MAX_ENTRIES)


if __name__ == "__main__":
    unittest.main()

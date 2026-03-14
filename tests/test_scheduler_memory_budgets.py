import unittest

from core.request import Request
from core.scheduler import DupeFilter, Scheduler, SchedulerConfig


class DupeFilterBudgetTests(unittest.TestCase):
    def test_dupefilter_is_bounded_and_evicts_old_entries(self) -> None:
        dupe = DupeFilter(persist=False, max_entries=3)
        urls = [f"https://example.com/{idx}" for idx in range(4)]

        for url in urls:
            self.assertFalse(dupe.request_seen(Request(url=url)))

        stats = dupe.get_stats()
        self.assertEqual(stats["size"], 3)
        self.assertGreaterEqual(stats["evicted_fingerprints"], 1)
        self.assertLessEqual(len(dupe), 3)

        # 最早元素应已被逐出；首次重入视为新请求，第二次重入为重复请求。
        self.assertFalse(dupe.request_seen(Request(url=urls[0])))
        self.assertTrue(dupe.request_seen(Request(url=urls[0])))


class SchedulerMemoryBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_scheduler_skips_domain_bookkeeping_without_limit(self) -> None:
        scheduler = Scheduler(
            SchedulerConfig(
                max_queue_size=64,
                max_requests_per_domain=0,
                max_dupefilter_entries=64,
                persist=False,
            )
        )
        await scheduler.open()
        try:
            for idx in range(16):
                ok = await scheduler.enqueue_request(Request(url=f"https://d{idx}.example.com/page"))
                self.assertTrue(ok)

            stats = scheduler.get_stats()
            self.assertEqual(stats["domains"], 0)
            self.assertEqual(stats["queued"], 16)
        finally:
            await scheduler.close()

    async def test_scheduler_reports_queue_full_and_keeps_dupefilter_bounded(self) -> None:
        scheduler = Scheduler(
            SchedulerConfig(
                max_queue_size=2,
                max_requests_per_domain=0,
                max_dupefilter_entries=3,
                persist=False,
            )
        )
        await scheduler.open()
        try:
            outcomes = []
            for idx in range(5):
                ok = await scheduler.enqueue_request(Request(url=f"https://overflow.example.com/{idx}"))
                outcomes.append(ok)

            self.assertEqual(outcomes[:2], [True, True])
            self.assertEqual(outcomes[2:], [False, False, False])

            stats = scheduler.get_stats()
            self.assertEqual(stats["queue_size"], 2)
            self.assertEqual(stats["dropped_queue_full"], 3)
            self.assertLessEqual(stats["dupefilter"]["size"], 3)
            self.assertGreaterEqual(stats["dupefilter"]["evicted_fingerprints"], 2)
        finally:
            await scheduler.close()

    async def test_scheduler_pressure_profile_trims_and_restores_budget(self) -> None:
        scheduler = Scheduler(
            SchedulerConfig(
                max_queue_size=10,
                max_requests_per_domain=0,
                max_dupefilter_entries=20,
                persist=False,
            )
        )
        await scheduler.open()
        try:
            for idx in range(10):
                ok = await scheduler.enqueue_request(Request(url=f"https://adaptive.example.com/{idx}"))
                self.assertTrue(ok)

            critical_update = scheduler.apply_pressure_profile("critical", {"links_max": 1})
            critical_stats = scheduler.get_stats()

            self.assertEqual(critical_update["level"], "critical")
            self.assertGreaterEqual(critical_update["trimmed_requests"], 1)
            self.assertLess(critical_stats["queue_max_size"], 10)
            self.assertLess(critical_stats["dupefilter"]["max_entries"], 20)
            self.assertLessEqual(critical_stats["queue_size"], critical_stats["queue_max_size"])
            self.assertGreaterEqual(critical_stats["pressure_queue_trimmed"], 1)

            normal_update = scheduler.apply_pressure_profile("normal")
            normal_stats = scheduler.get_stats()

            self.assertEqual(normal_update["level"], "normal")
            self.assertEqual(normal_stats["queue_max_size"], 10)
            self.assertEqual(normal_stats["dupefilter"]["max_entries"], 20)
            self.assertGreaterEqual(normal_stats["pressure_adjustments"], 2)
        finally:
            await scheduler.close()


if __name__ == "__main__":
    unittest.main()

import unittest

from core.metrics import MetricsCollector


class MetricsCollectorBudgetTests(unittest.TestCase):
    def test_domain_and_proxy_windows_are_bounded(self) -> None:
        collector = MetricsCollector(
            max_history=10,
            max_domains=2,
            max_proxies=2,
        )

        collector.record_request("https://a.example.com/1", 200, 20, proxy="p1")
        collector.record_request("https://b.example.com/1", 200, 20, proxy="p2")
        collector.record_request("https://c.example.com/1", 500, 20, proxy="p3")

        domain_keys = list(collector._by_domain.keys())
        proxy_keys = list(collector._proxy_stats.keys())

        self.assertEqual(domain_keys, ["b.example.com", "c.example.com"])
        self.assertEqual(proxy_keys, ["p2", "p3"])

    def test_recent_domain_access_refreshes_lru(self) -> None:
        collector = MetricsCollector(
            max_history=10,
            max_domains=2,
            max_proxies=2,
        )

        collector.record_request("https://a.example.com/1", 200, 20)
        collector.record_request("https://b.example.com/1", 200, 20)
        collector.record_request("https://a.example.com/2", 200, 20)
        collector.record_request("https://c.example.com/1", 200, 20)

        domain_keys = list(collector._by_domain.keys())
        self.assertEqual(domain_keys, ["a.example.com", "c.example.com"])
        self.assertNotIn("b.example.com", collector._by_domain)


if __name__ == "__main__":
    unittest.main()

import unittest

from core.metrics import (
    MetricsCollector,
    clear_budget_telemetry_provider,
    export_prometheus_metrics,
    set_budget_telemetry_provider,
)


class PrometheusBudgetMetricsTests(unittest.TestCase):
    def test_collector_exports_budget_telemetry_metrics(self) -> None:
        collector = MetricsCollector(max_history=4, max_domains=4, max_proxies=4)
        collector.record_request("https://example.com", 200, 12)

        metrics = collector.to_prometheus(
            budget_telemetry={
                "health_score": 88,
                "pressure_level": "high",
                "alerts": ["runtime_events_dropped", "budget_near_capacity"],
                "utilization": {
                    "state_pages_ratio": 0.75,
                    "event_store_ratio": 1.0,
                },
            }
        )

        self.assertIn("web_rooter_budget_health_score 88", metrics)
        self.assertIn("web_rooter_budget_pressure_level 2", metrics)
        self.assertIn('web_rooter_budget_utilization_ratio{surface="state_pages_ratio"} 0.7500', metrics)
        self.assertIn('web_rooter_budget_alert_active{alert="runtime_events_dropped"} 1', metrics)

    def test_global_export_uses_registered_budget_provider(self) -> None:
        set_budget_telemetry_provider(
            lambda: {
                "health_score": 77,
                "pressure_level": "critical",
                "alerts": ["pressure_critical"],
                "utilization": {"artifact_nodes_ratio": 0.95},
            }
        )
        try:
            metrics = export_prometheus_metrics()
        finally:
            clear_budget_telemetry_provider()

        self.assertIn("web_rooter_budget_health_score 77", metrics)
        self.assertIn("web_rooter_budget_pressure_level 3", metrics)
        self.assertIn('web_rooter_budget_alert_active{alert="pressure_critical"} 1', metrics)


if __name__ == "__main__":
    unittest.main()

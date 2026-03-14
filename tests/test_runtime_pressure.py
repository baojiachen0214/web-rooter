import unittest

from core.runtime_pressure import RuntimePressureController, RuntimePressurePolicy


class RuntimePressureControllerTests(unittest.TestCase):
    def test_memory_thresholds_control_level(self) -> None:
        policy = RuntimePressurePolicy(
            elevated_rss_mb=100,
            high_rss_mb=200,
            critical_rss_mb=300,
        )
        controller = RuntimePressureController(policy=policy)

        normal = controller.evaluate(memory_usage={"rss_mb": 50})
        self.assertEqual(normal["level"], "normal")

        elevated = controller.evaluate(memory_usage={"rss_mb": 150})
        self.assertEqual(elevated["level"], "elevated")

        high = controller.evaluate(memory_usage={"rss_mb": 250})
        self.assertEqual(high["level"], "high")

        critical = controller.evaluate(memory_usage={"rss_mb": 350})
        self.assertEqual(critical["level"], "critical")
        self.assertFalse(critical["limits"]["allow_browser_fallback"])

    def test_error_rate_promotes_pressure_level(self) -> None:
        policy = RuntimePressurePolicy(
            min_error_samples=4,
            error_window_size=8,
            elevated_error_rate=0.25,
            high_error_rate=0.5,
            critical_error_rate=0.75,
        )
        controller = RuntimePressureController(policy=policy)

        outcomes = [False, False, True, False]  # error rate = 0.75
        for item in outcomes:
            controller.record_outcome(success=item)

        snapshot = controller.evaluate(memory_usage={"rss_mb": 10})
        self.assertEqual(snapshot["level"], "critical")
        self.assertGreaterEqual(snapshot["errors"]["error_rate"], 0.75)

    def test_clear_resets_runtime_state(self) -> None:
        controller = RuntimePressureController(
            policy=RuntimePressurePolicy(min_error_samples=2, error_window_size=4)
        )
        controller.record_outcome(False)
        controller.record_outcome(False)
        before = controller.evaluate(memory_usage={"rss_mb": 0})
        self.assertIn(before["level"], {"elevated", "high", "critical", "normal"})

        controller.clear()
        after = controller.snapshot()
        self.assertEqual(after["level"], "normal")
        self.assertEqual(after["errors"]["samples"], 0)
        self.assertEqual(after["errors"]["failures"], 0)


if __name__ == "__main__":
    unittest.main()

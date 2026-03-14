import unittest

from core.runtime_events import RuntimeEventBudget, RuntimeEventStream


class RuntimeEventStreamTests(unittest.TestCase):
    def test_overflow_keeps_latest_and_tracks_drops(self) -> None:
        stream = RuntimeEventStream(RuntimeEventBudget(max_events=3))
        for idx in range(5):
            stream.record(
                event_type="tick",
                source="test",
                payload={"idx": idx},
            )

        snapshot = stream.snapshot(limit=10)
        seqs = [item["seq"] for item in snapshot["events"]]

        self.assertEqual(seqs, [3, 4, 5])
        self.assertEqual(snapshot["stats"]["dropped_events"], 2)
        self.assertEqual(snapshot["stats"]["total_recorded"], 5)
        self.assertEqual(snapshot["stats"]["store_size"], 3)

    def test_filters_and_since_cursor(self) -> None:
        stream = RuntimeEventStream(RuntimeEventBudget(max_events=20))
        stream.record("visit_start", "research_kernel", {"url": "https://a"})
        stream.record("visit_complete", "research_kernel", {"url": "https://a"})
        stream.record("fetch_html_complete", "research_kernel", {"url": "https://a"})

        filtered = stream.snapshot(limit=10, event_type="visit_complete")
        self.assertEqual(len(filtered["events"]), 1)
        self.assertEqual(filtered["events"][0]["event_type"], "visit_complete")

        cursor = filtered["events"][0]["seq"]
        delta = stream.snapshot(limit=10, since_seq=cursor)
        delta_types = [item["event_type"] for item in delta["events"]]
        self.assertEqual(delta_types, ["fetch_html_complete"])
        self.assertEqual(delta["next_cursor"], delta["events"][-1]["seq"])

    def test_payload_is_compacted(self) -> None:
        stream = RuntimeEventStream(
            RuntimeEventBudget(
                max_events=10,
                max_payload_items=2,
                max_payload_depth=2,
                max_payload_string_chars=8,
            )
        )
        stream.record(
            "payload_test",
            "research_kernel",
            payload={
                "long_text": "abcdefghijklmn",
                "nested": {"deep": {"too": "deep"}},
                "items": [1, 2, 3, 4],
            },
        )

        event = stream.snapshot(limit=1)["events"][0]
        payload = event["payload"]
        self.assertTrue(str(payload["long_text"]).startswith("abcdefgh"))
        self.assertTrue(str(payload["long_text"]).endswith("[truncated]"))
        self.assertIn("nested", payload)


if __name__ == "__main__":
    unittest.main()

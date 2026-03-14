import tempfile
import unittest
from pathlib import Path
from core.global_context import GlobalDeepContextStore
from core.result_queue import ResultQueue
from core.scheduler import (
    DEFAULT_DUPEFILTER_MAX_ENTRIES,
    DEFAULT_SCHEDULER_MAX_QUEUE_SIZE,
    Scheduler,
    SchedulerConfig,
)
from core.search.graph import MindSearchStyleAgent, SearchGraph


class _FakeSearchEngine:
    async def search(self, query, deduplicate=True, parallel=True):
        return [{"title": f"{query}-{idx}", "url": f"https://example.com/{idx}"} for idx in range(8)]


class SchedulerBudgetTests(unittest.TestCase):
    def test_scheduler_uses_bounded_default_queue(self) -> None:
        config = SchedulerConfig()
        self.assertEqual(config.max_queue_size, DEFAULT_SCHEDULER_MAX_QUEUE_SIZE)
        self.assertGreater(config.max_queue_size, 0)

    def test_scheduler_uses_bounded_default_dupefilter(self) -> None:
        config = SchedulerConfig()
        self.assertEqual(config.max_dupefilter_entries, DEFAULT_DUPEFILTER_MAX_ENTRIES)
        self.assertGreater(config.max_dupefilter_entries, 0)

    def test_scheduler_coerces_non_positive_budgets(self) -> None:
        scheduler = Scheduler(
            SchedulerConfig(
                max_queue_size=0,
                max_dupefilter_entries=0,
                persist=False,
            )
        )
        stats = scheduler.get_stats()
        self.assertEqual(stats["queue_max_size"], DEFAULT_SCHEDULER_MAX_QUEUE_SIZE)
        self.assertEqual(stats["dupefilter"]["max_entries"], DEFAULT_DUPEFILTER_MAX_ENTRIES)


class SearchGraphBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_execute_all_caps_results_and_drops_old_events(self) -> None:
        graph = SearchGraph(
            search_engine=_FakeSearchEngine(),
            max_event_queue_size=2,
            max_results_per_node=3,
            max_event_results=1,
        )
        graph.add_query("alpha", is_root=True)
        graph.add_query("beta")

        await graph.execute_all()

        snapshot = graph.get_results()
        self.assertEqual(snapshot["stats"]["dropped_events"], 2)
        self.assertEqual(snapshot["stats"]["event_queue_size"], 2)

        for node in snapshot["nodes"].values():
            self.assertLessEqual(len(node["results"]), 3)


class ResultQueueBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_drop_oldest_strategy_keeps_latest_items(self) -> None:
        queue = ResultQueue(maxsize=2, overflow_strategy="drop_oldest")
        self.assertTrue(queue.put_nowait({"idx": 1}))
        self.assertTrue(queue.put_nowait({"idx": 2}))
        self.assertTrue(queue.put_nowait({"idx": 3}))

        first = await queue.get_nowait()
        second = await queue.get_nowait()
        stats = queue.get_stats()

        self.assertEqual(first.data["idx"], 2)
        self.assertEqual(second.data["idx"], 3)
        self.assertEqual(stats["items_dropped"], 1)
        self.assertEqual(stats["current_size"], 0)


class GlobalContextPersistenceTests(unittest.TestCase):
    def test_persisted_context_is_compacted_and_tail_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            persist_path = Path(tmpdir) / "context.jsonl"
            store = GlobalDeepContextStore(
                max_events=3,
                persist_path=persist_path,
                max_persisted_events=4,
            )

            for idx in range(6):
                store.record(
                    event_type="tick",
                    source="test",
                    payload={"idx": idx},
                )

            line_count = len(persist_path.read_text(encoding="utf-8").splitlines())
            self.assertLessEqual(line_count, 4)

            reloaded = GlobalDeepContextStore(
                max_events=3,
                persist_path=persist_path,
                max_persisted_events=4,
            )
            snapshot = reloaded.snapshot(limit=10)

            self.assertEqual(snapshot["stats"]["store_size"], 3)
            self.assertEqual(snapshot["events"][-1]["payload"]["idx"], 5)


class SearchHistoryBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_history_is_compact_and_bounded(self) -> None:
        agent = MindSearchStyleAgent(
            search_engine=_FakeSearchEngine(),
            max_turns=2,
            history_limit=2,
        )

        await agent.research("alpha topic")
        await agent.research("beta topic")
        await agent.research("gamma topic")

        history = list(agent._search_history)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["query"], "beta topic")
        self.assertEqual(history[1]["query"], "gamma topic")
        self.assertNotIn("results", history[-1])
        self.assertIn("stats", history[-1])


if __name__ == "__main__":
    unittest.main()

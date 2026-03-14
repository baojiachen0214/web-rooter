import unittest

from core.search.graph import SearchGraph
from core.search.mindsearch_pipeline import MindSearchPipeline


class SearchPressureAdaptationTests(unittest.TestCase):
    def test_mindsearch_pipeline_reduces_budgets_under_critical_pressure(self) -> None:
        pipeline = MindSearchPipeline(
            max_turns=4,
            max_branches=5,
            num_results=12,
            crawl_top=3,
            max_nodes=20,
            pressure_level="critical",
            pressure_limits={
                "allow_browser_fallback": False,
                "links_max": 4,
            },
        )

        self.assertEqual(pipeline.pressure_level, "critical")
        self.assertLessEqual(pipeline.max_turns, 2)
        self.assertLessEqual(pipeline.max_branches, 2)
        self.assertLessEqual(pipeline.max_nodes, 6)
        self.assertLessEqual(pipeline.num_results, 4)
        self.assertEqual(pipeline.crawl_top, 0)
        self.assertLessEqual(pipeline.max_stream_queue_size, 32)

    def test_search_graph_reduces_event_and_result_budgets_under_high_pressure(self) -> None:
        graph = SearchGraph(
            max_event_queue_size=200,
            max_results_per_node=15,
            max_event_results=5,
            pressure_level="high",
            pressure_limits={"links_max": 5},
        )
        stats = graph.get_stats()

        self.assertEqual(stats["pressure_level"], "high")
        self.assertLessEqual(stats["max_results_per_node"], 5)
        self.assertEqual(stats["dropped_events"], 0)


if __name__ == "__main__":
    unittest.main()

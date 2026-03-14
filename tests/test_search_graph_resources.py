import unittest

from core.search.graph import SearchGraph


class SearchGraphResourceBudgetTests(unittest.TestCase):
    def test_search_graph_avoids_unused_thread_pool_allocation(self) -> None:
        graph = SearchGraph(max_workers=3)
        stats = graph.get_stats()

        self.assertFalse(hasattr(graph, "executor"))
        self.assertEqual(stats["max_workers"], 3)


if __name__ == "__main__":
    unittest.main()

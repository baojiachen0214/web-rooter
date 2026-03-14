import unittest

from core.artifact_graph import ArtifactGraph, ArtifactGraphBudget
from core.runtime_events import RuntimeEventBudget, RuntimeEventStream
from core.runtime_state import AgentRuntimeState, RuntimeStateBudget


class BudgetSoakTests(unittest.TestCase):
    def test_high_volume_operations_remain_bounded(self) -> None:
        state = AgentRuntimeState(
            RuntimeStateBudget(
                max_pages=16,
                max_total_content_chars=500,
                max_page_content_chars=60,
                max_visited_urls=24,
            )
        )
        events = RuntimeEventStream(RuntimeEventBudget(max_events=32))
        graph = ArtifactGraph(
            ArtifactGraphBudget(
                max_nodes=20,
                max_edges=40,
                max_out_edges_per_node=4,
            )
        )

        source_id = graph.make_node_id("session", "runtime")
        graph.upsert_node(node_id=source_id, kind="session", label="runtime", attrs={})

        for idx in range(1200):
            state.mark_visited(f"https://visited-{idx}.example.com")
            state.store_page(
                url=f"https://page-{idx}.example.com",
                title=f"page-{idx}",
                content=("payload-" * 40),
                content_chars=320,
                links=[{"href": f"https://link-{idx}.example.com/{j}", "text": "x"} for j in range(10)],
                extracted_info={"idx": idx, "meta": {"large": "x" * 200}},
            )
            events.record("tick", "soak", {"idx": idx, "payload": "x" * 120})

            node_id = graph.make_node_id("page", f"https://page-{idx}.example.com")
            graph.upsert_node(node_id=node_id, kind="page", label=f"page-{idx}", attrs={"idx": idx})
            graph.upsert_edge(source=source_id, target=node_id, relation="contains", attrs={"idx": idx})

        state_stats = state.get_stats()
        event_stats = events.get_stats()
        graph_stats = graph.get_stats()

        self.assertLessEqual(state_stats["pages"], state_stats["budget"]["max_pages"])
        self.assertLessEqual(state_stats["visited_urls"], state_stats["budget"]["max_visited_urls"])
        self.assertLessEqual(
            state_stats["total_content_chars"],
            state_stats["budget"]["max_total_content_chars"],
        )
        self.assertGreater(state_stats["counters"]["pages_evicted"], 0)
        self.assertGreater(state_stats["counters"]["content_truncated"], 0)

        self.assertLessEqual(event_stats["store_size"], event_stats["max_events"])
        self.assertGreater(event_stats["dropped_events"], 0)

        self.assertLessEqual(graph_stats["nodes"], graph_stats["budget"]["max_nodes"])
        self.assertLessEqual(graph_stats["edges"], graph_stats["budget"]["max_edges"])
        self.assertGreater(graph_stats["counters"]["nodes_evicted"], 0)
        self.assertGreater(graph_stats["counters"]["edges_evicted_total"], 0)


if __name__ == "__main__":
    unittest.main()

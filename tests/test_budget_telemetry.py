import unittest

from core.artifact_graph import ArtifactGraph, ArtifactGraphBudget
from core.research_kernel import ResearchKernel
from core.runtime_events import RuntimeEventBudget, RuntimeEventStream
from core.runtime_state import AgentRuntimeState, RuntimeStateBudget


class BudgetTelemetryTests(unittest.TestCase):
    def test_budget_telemetry_reports_alerts_and_utilization(self) -> None:
        kernel = ResearchKernel()
        kernel._state = AgentRuntimeState(
            RuntimeStateBudget(
                max_pages=4,
                max_total_content_chars=80,
                max_page_content_chars=20,
                max_visited_urls=4,
            )
        )
        kernel._events = RuntimeEventStream(RuntimeEventBudget(max_events=5))
        kernel._artifacts = ArtifactGraph(
            ArtifactGraphBudget(
                max_nodes=4,
                max_edges=6,
                max_out_edges_per_node=2,
            )
        )
        kernel._artifact_session_node_id = kernel._artifacts.make_node_id("session", "runtime")
        kernel._ensure_artifact_session_node()

        for idx in range(10):
            kernel._events.record("tick", "test", {"idx": idx})
            kernel._state.mark_visited(f"https://v{idx}.example.com")
            kernel._state.store_page(
                url=f"https://p{idx}.example.com",
                title=f"page-{idx}",
                content="x" * 40,
                content_chars=40,
                links=[{"href": f"https://l{idx}.example.com/{j}", "text": "x"} for j in range(6)],
                extracted_info={"idx": idx},
            )

            node_id = kernel._artifacts.make_node_id("page", f"https://p{idx}.example.com")
            kernel._artifacts.upsert_node(
                node_id=node_id,
                kind="page",
                label=f"p{idx}",
                attrs={"url": f"https://p{idx}.example.com"},
            )
            kernel._artifacts.upsert_edge(
                source=kernel._artifact_session_node_id,
                target=node_id,
                relation="contains",
                attrs={"idx": idx},
            )

        snapshot = kernel.get_budget_telemetry_snapshot(refresh=False)
        alerts = set(snapshot.get("alerts", []))
        utilization = snapshot.get("utilization", {})

        self.assertIn("runtime_events_dropped", alerts)
        self.assertIn("runtime_state_pages_evicted", alerts)
        self.assertIn("runtime_state_content_truncated", alerts)
        self.assertIn("artifact_nodes_evicted", alerts)
        self.assertIn("artifact_edges_evicted", alerts)
        self.assertIn("budget_near_capacity", alerts)

        self.assertGreater(utilization.get("event_store_ratio", 0), 0.9)
        self.assertGreater(utilization.get("state_pages_ratio", 0), 0.9)
        self.assertGreater(utilization.get("artifact_nodes_ratio", 0), 0.9)
        self.assertLess(snapshot.get("health_score", 100), 100)


if __name__ == "__main__":
    unittest.main()

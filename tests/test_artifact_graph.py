import unittest

from core.artifact_graph import ArtifactGraph, ArtifactGraphBudget


class ArtifactGraphBudgetTests(unittest.TestCase):
    def test_node_eviction_removes_related_edges(self) -> None:
        graph = ArtifactGraph(
            ArtifactGraphBudget(
                max_nodes=2,
                max_edges=10,
                max_out_edges_per_node=4,
            )
        )

        graph.upsert_node(node_id="n1", kind="page", label="node1", attrs={"url": "https://a"})
        graph.upsert_node(node_id="n2", kind="page", label="node2", attrs={"url": "https://b"})
        graph.upsert_edge(source="n1", target="n2", relation="links_to", attrs={})

        # Inserting n3 should evict the oldest node n1 and remove its edges.
        graph.upsert_node(node_id="n3", kind="page", label="node3", attrs={"url": "https://c"})

        snapshot = graph.snapshot(node_limit=10, edge_limit=10)
        node_ids = {item["id"] for item in snapshot["nodes"]}

        self.assertEqual(node_ids, {"n2", "n3"})
        self.assertEqual(snapshot["stats"]["nodes"], 2)
        self.assertEqual(snapshot["stats"]["edges"], 0)

    def test_outgoing_edge_budget_keeps_latest_relations(self) -> None:
        graph = ArtifactGraph(
            ArtifactGraphBudget(
                max_nodes=10,
                max_edges=20,
                max_out_edges_per_node=2,
            )
        )

        for node_id in ["src", "a", "b", "c"]:
            graph.upsert_node(node_id=node_id, kind="url", label=node_id, attrs={})

        graph.upsert_edge(source="src", target="a", relation="links_to", attrs={})
        graph.upsert_edge(source="src", target="b", relation="links_to", attrs={})
        graph.upsert_edge(source="src", target="c", relation="links_to", attrs={})

        snapshot = graph.snapshot(node_limit=10, edge_limit=10)
        links = [
            item for item in snapshot["edges"]
            if item["source"] == "src" and item["relation"] == "links_to"
        ]
        targets = {item["target"] for item in links}

        self.assertEqual(len(links), 2)
        self.assertEqual(targets, {"b", "c"})

    def test_snapshot_kind_filter(self) -> None:
        graph = ArtifactGraph(ArtifactGraphBudget(max_nodes=10, max_edges=10))
        graph.upsert_node(node_id="session", kind="session", label="runtime", attrs={})
        graph.upsert_node(node_id="page1", kind="page", label="Page 1", attrs={"url": "https://example.com"})
        graph.upsert_node(node_id="url1", kind="url", label="Url 1", attrs={"url": "https://example.com/a"})
        graph.upsert_edge(source="page1", target="url1", relation="links_to", attrs={})

        filtered = graph.snapshot(node_limit=10, edge_limit=10, node_kind="page")
        self.assertEqual(len(filtered["nodes"]), 1)
        self.assertEqual(filtered["nodes"][0]["id"], "page1")
        self.assertEqual(filtered["edges"], [])


if __name__ == "__main__":
    unittest.main()

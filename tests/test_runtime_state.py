import unittest

from core.runtime_state import AgentRuntimeState, RuntimeStateBudget


class RuntimeStateTests(unittest.TestCase):
    def test_eviction_respects_total_content_budget(self) -> None:
        state = AgentRuntimeState(
            RuntimeStateBudget(
                max_pages=3,
                max_total_content_chars=10,
                max_page_content_chars=10,
                max_visited_urls=2,
            )
        )

        state.store_page(url="https://a", title="A", content="12345", content_chars=5)
        state.store_page(url="https://b", title="B", content="67890", content_chars=5)
        state.store_page(url="https://c", title="C", content="xyz", content_chars=3)

        urls = [item["url"] for item in state.get_knowledge_base()]
        self.assertEqual(urls, ["https://b", "https://c"])

    def test_store_page_tracks_original_length_and_truncation(self) -> None:
        state = AgentRuntimeState(
            RuntimeStateBudget(
                max_pages=4,
                max_total_content_chars=100,
                max_page_content_chars=6,
            )
        )

        snapshot = state.store_page(
            url="https://example.com",
            title="Example",
            content="abcdefghijk",
            content_chars=11,
            links=[{"href": "https://example.com/x", "text": "x"}],
            extracted_info={"json_ld": {"very": "large"}},
        )

        self.assertTrue(snapshot.truncated)
        self.assertEqual(snapshot.content, "abcdef")
        self.assertEqual(snapshot.content_chars, 11)

    def test_visited_urls_are_bounded(self) -> None:
        state = AgentRuntimeState(
            RuntimeStateBudget(
                max_pages=4,
                max_total_content_chars=100,
                max_page_content_chars=20,
                max_visited_urls=2,
            )
        )

        state.mark_visited("https://a")
        state.mark_visited("https://b")
        state.mark_visited("https://c")

        self.assertEqual(state.get_visited_urls(), ["https://b", "https://c"])

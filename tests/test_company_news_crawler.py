"""
Tests for core.company_news_crawler and the NewsCountChangeProcessor.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from core.company_news_crawler import (
    CompanyRecord,
    CompanyNewsCrawler,
    PageCrawlResult,
    _build_page_url,
    _count_news_links,
    _extract_next_page_url,
    build_verification_report,
    crawl_news_pages,
    run_batch,
)
from core.postprocess import (
    NewsCountChangeProcessor,
    PostProcessContext,
    PostProcessorRegistry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# CompanyRecord tests
# ---------------------------------------------------------------------------

class TestCompanyRecord(unittest.TestCase):
    def test_company_id_defaults_to_safe_name(self):
        rec = CompanyRecord(name="示例科技 Inc.", url="https://example.com")
        self.assertIn("示例科技", rec.company_id)
        # Spaces replaced, special chars removed
        self.assertNotIn(" ", rec.company_id)

    def test_explicit_company_id_respected(self):
        rec = CompanyRecord(name="A", url="https://a.com", company_id="custom-id")
        self.assertEqual(rec.company_id, "custom-id")

    def test_news_count_before_defaults_to_zero(self):
        rec = CompanyRecord(name="B", url="https://b.com")
        self.assertEqual(rec.news_count_before, 0)


# ---------------------------------------------------------------------------
# Pagination URL builder tests
# ---------------------------------------------------------------------------

class TestBuildPageUrl(unittest.TestCase):
    def test_query_param_replacement(self):
        base = "https://example.com/news?page=1"
        result = _build_page_url(base, 3)
        self.assertIn("page=3", result)
        self.assertNotIn("page=1", result)

    def test_path_segment_replacement(self):
        base = "https://example.com/news/list/1"
        result = _build_page_url(base, 5)
        self.assertIn("/list/5", result)

    def test_appends_page_param_when_no_existing_pattern(self):
        base = "https://example.com/news"
        result = _build_page_url(base, 2)
        self.assertIn("page=2", result)

    def test_page_segment_in_path(self):
        base = "https://example.com/page/1/items"
        result = _build_page_url(base, 4)
        self.assertIn("/page/4/", result)


# ---------------------------------------------------------------------------
# HTML helpers tests
# ---------------------------------------------------------------------------

class TestExtractNextPageUrl(unittest.TestCase):
    def test_rel_next_link(self):
        html = '<a href="/news?page=2" rel="next">下一页</a>'
        result = _extract_next_page_url(html, "https://example.com/news")
        self.assertIsNotNone(result)
        self.assertIn("page=2", result)

    def test_no_rel_next_returns_none(self):
        html = "<p>No pagination here</p>"
        result = _extract_next_page_url(html, "https://example.com/news")
        self.assertIsNone(result)

    def test_relative_href_resolved(self):
        html = '<a href="/news/list/3" rel="next">next</a>'
        result = _extract_next_page_url(html, "https://example.com/news/list/2")
        self.assertEqual(result, "https://example.com/news/list/3")


class TestCountNewsLinks(unittest.TestCase):
    def test_counts_news_article_links(self):
        html = """
        <a href="/news/detail/123">Title 1</a>
        <a href="/article/456">Title 2</a>
        <a href="/other">Other</a>
        """
        count = _count_news_links(html)
        self.assertEqual(count, 2)

    def test_empty_html_returns_zero(self):
        self.assertEqual(_count_news_links(""), 0)

    def test_no_news_links(self):
        self.assertEqual(_count_news_links('<a href="/about">About</a>'), 0)


# ---------------------------------------------------------------------------
# crawl_news_pages tests (mocked HTTP)
# ---------------------------------------------------------------------------

class TestCrawlNewsPages(unittest.TestCase):
    def _make_html(self, page: int, has_next: bool = True) -> str:
        next_link = f'<a href="/news?page={page + 1}" rel="next">next</a>' if has_next else ""
        return (
            f"<html><body>"
            f'<a href="/news/detail/{page}01">Article {page}01</a>'
            f'<a href="/news/detail/{page}02">Article {page}02</a>'
            f"{next_link}"
            f"</body></html>"
        )

    @patch("core.company_news_crawler._fetch_html_http")
    def test_crawls_multiple_pages(self, mock_http):
        # Return 3 pages then stop
        responses = [
            (200, self._make_html(1, has_next=True)),
            (200, self._make_html(2, has_next=True)),
            (200, self._make_html(3, has_next=False)),
            (-1, ""),  # page 4 → no content, stops crawl
        ]
        idx = {"val": 0}

        async def side_effect(url, timeout=20):
            i = idx["val"]
            idx["val"] += 1
            if i < len(responses):
                return responses[i]
            return -1, ""

        mock_http.side_effect = side_effect

        with tempfile.TemporaryDirectory() as tmp:
            results = _run(crawl_news_pages(
                company_url="https://example.com/news?page=1",
                output_dir=Path(tmp),
                company_id="example",
                max_pages=5,
                request_delay=0,
            ))

        success_pages = [r for r in results if r.success]
        self.assertGreaterEqual(len(success_pages), 3)

    @patch("core.company_news_crawler._fetch_html_http")
    @patch("core.company_news_crawler._fetch_html_browser")
    def test_browser_fallback_on_403(self, mock_browser, mock_http):
        async def http_fail(url, timeout=20):
            return 403, ""

        async def browser_ok(url, timeout_ms=20000):
            return 200, '<a href="/news/detail/1">article</a>'

        mock_http.side_effect = http_fail
        mock_browser.side_effect = browser_ok

        with tempfile.TemporaryDirectory() as tmp:
            results = _run(crawl_news_pages(
                company_url="https://example.com/news",
                output_dir=Path(tmp),
                company_id="fallback_co",
                max_pages=1,
                request_delay=0,
            ))

        self.assertTrue(results[0].success)
        self.assertTrue(results[0].via_browser)

    @patch("core.company_news_crawler._fetch_html_http")
    def test_output_files_created(self, mock_http):
        async def ok(url, timeout=20):
            return 200, '<a href="/news/detail/1">article</a>'

        mock_http.side_effect = ok

        with tempfile.TemporaryDirectory() as tmp:
            _run(crawl_news_pages(
                company_url="https://example.com/news",
                output_dir=Path(tmp),
                company_id="filetest",
                max_pages=2,
                request_delay=0,
            ))
            html_files = list(Path(tmp).glob("filetest/page_*.html"))
            meta_files = list(Path(tmp).glob("filetest/page_*.meta.json"))
            self.assertGreaterEqual(len(html_files), 1)
            self.assertGreaterEqual(len(meta_files), 1)

            # Verify meta.json structure
            meta = json.loads(meta_files[0].read_text())
            self.assertIn("company_id", meta)
            self.assertIn("page_number", meta)
            self.assertIn("citation", meta)
            self.assertIn("fetched_at", meta)


# ---------------------------------------------------------------------------
# CompanyNewsCrawler integration tests (mocked IO)
# ---------------------------------------------------------------------------

class TestCompanyNewsCrawler(unittest.TestCase):
    @patch("core.company_news_crawler.crawl_news_pages")
    def test_run_records_job_and_stats(self, mock_crawl):
        async def fake_crawl(**kwargs):
            return [
                PageCrawlResult(
                    company_id=kwargs["company_id"],
                    page_number=1,
                    url="https://example.com",
                    html="<html/>",
                    news_links=5,
                    success=True,
                )
            ]

        mock_crawl.side_effect = fake_crawl

        companies = [
            CompanyRecord(name="公司A", url="https://a.com", news_count_before=3),
            CompanyRecord(name="公司B", url="https://b.com", news_count_before=10),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            crawler = CompanyNewsCrawler(
                output_dir=Path(tmp),
                max_pages=3,
                batch_size=50,
                request_delay=0,
            )
            stats = _run(crawler.run(companies))

        self.assertEqual(stats["success_count"], 2)
        self.assertEqual(stats["failed_count"], 0)

    @patch("core.company_news_crawler.crawl_news_pages")
    def test_checkpoint_saves_completed_ids(self, mock_crawl):
        async def fake_crawl(**kwargs):
            return [PageCrawlResult(
                company_id=kwargs["company_id"],
                page_number=1,
                url="x",
                html="<html/>",
                news_links=1,
                success=True,
            )]

        mock_crawl.side_effect = fake_crawl

        companies = [CompanyRecord(name="公司C", url="https://c.com", company_id="co_c")]

        with tempfile.TemporaryDirectory() as tmp:
            crawler = CompanyNewsCrawler(
                output_dir=Path(tmp),
                max_pages=1,
                request_delay=0,
                checkpoint_dir=Path(tmp) / "cp",
            )
            _run(crawler.run(companies))

            # Checkpoint directory should contain at least one file
            cp_files = list((Path(tmp) / "cp").glob("*.pkl"))
            self.assertGreater(len(cp_files), 0)


# ---------------------------------------------------------------------------
# build_verification_report tests
# ---------------------------------------------------------------------------

class TestBuildVerificationReport(unittest.TestCase):
    def _write_summary(self, tmp: str, company_id: str, data: dict) -> None:
        company_dir = Path(tmp) / company_id
        company_dir.mkdir(parents=True, exist_ok=True)
        (company_dir / "crawl_summary.json").write_text(
            json.dumps(data), encoding="utf-8"
        )

    def test_improved_company_counted(self):
        companies = [CompanyRecord(name="A", url="x", company_id="co_a", news_count_before=5)]
        with tempfile.TemporaryDirectory() as tmp:
            self._write_summary(tmp, "co_a", {"total_news_links": 20, "pages_fetched": 3})
            report = build_verification_report(companies, Path(tmp))
        self.assertEqual(report["improved"], 1)
        self.assertEqual(report["unchanged"], 0)
        self.assertEqual(report["missing"], 0)

    def test_unchanged_company_counted(self):
        companies = [CompanyRecord(name="B", url="x", company_id="co_b", news_count_before=20)]
        with tempfile.TemporaryDirectory() as tmp:
            self._write_summary(tmp, "co_b", {"total_news_links": 10, "pages_fetched": 2})
            report = build_verification_report(companies, Path(tmp))
        self.assertEqual(report["improved"], 0)
        self.assertEqual(report["unchanged"], 1)

    def test_missing_company_counted(self):
        companies = [CompanyRecord(name="C", url="x", company_id="co_c")]
        with tempfile.TemporaryDirectory() as tmp:
            report = build_verification_report(companies, Path(tmp))
        self.assertEqual(report["missing"], 1)
        self.assertIn("co_c", report["missing_company_ids"])

    def test_report_file_written(self):
        companies = [CompanyRecord(name="D", url="x", company_id="co_d", news_count_before=0)]
        with tempfile.TemporaryDirectory() as tmp:
            self._write_summary(tmp, "co_d", {"total_news_links": 5, "pages_fetched": 1})
            build_verification_report(companies, Path(tmp))
            report_path = Path(tmp) / "verification_report.json"
            self.assertTrue(report_path.exists())
            data = json.loads(report_path.read_text())
            self.assertIn("generated_at", data)


# ---------------------------------------------------------------------------
# NewsCountChangeProcessor tests
# ---------------------------------------------------------------------------

class TestNewsCountChangeProcessor(unittest.TestCase):
    def setUp(self):
        self.processor = NewsCountChangeProcessor()
        self.ctx = PostProcessContext(query="test", mode="crawl")

    def test_improved_companies_counted(self):
        result = {
            "results": [
                {"news_count_before": 5, "news_links_after": 20},
                {"news_count_before": 3, "news_links_after": 10},
            ]
        }
        out = self.processor.process(result, self.ctx)
        self.assertEqual(out["quality"]["companies_improved"], 2)
        self.assertEqual(out["quality"]["companies_unchanged"], 0)
        self.assertEqual(out["quality"]["total_increase"], 22)

    def test_unchanged_companies_counted(self):
        result = {
            "results": [
                {"news_count_before": 50, "news_links_after": 10},
            ]
        }
        out = self.processor.process(result, self.ctx)
        self.assertEqual(out["quality"]["companies_improved"], 0)
        self.assertEqual(out["quality"]["companies_unchanged"], 1)

    def test_empty_results_handled(self):
        out = self.processor.process({"results": []}, self.ctx)
        self.assertEqual(out["quality"]["companies_improved"], 0)

    def test_missing_results_key_handled(self):
        out = self.processor.process({}, self.ctx)
        self.assertIn("quality", out)

    def test_processor_registered_in_registry(self):
        registry = PostProcessorRegistry()
        self.assertIn("news_count_change", registry.list_processors())


if __name__ == "__main__":
    unittest.main()

import unittest

from core.research_kernel import ResearchKernel


class ResearchKernelURLNormalizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_visit_rejects_relative_url(self) -> None:
        kernel = ResearchKernel()
        result = await kernel.visit("/s?wd=example")
        self.assertFalse(result.success)
        self.assertTrue(str(result.error or "").startswith("invalid_url:"))

    async def test_fetch_html_rejects_relative_url(self) -> None:
        kernel = ResearchKernel()
        result = await kernel.fetch_html("/s?wd=example")
        self.assertFalse(result.success)
        self.assertTrue(str(result.error or "").startswith("invalid_url:"))

    def test_normalize_url_adds_https_for_host_like_input(self) -> None:
        kernel = ResearchKernel()
        normalized = kernel.normalize_url("example.com/path")
        self.assertEqual("https://example.com/path", normalized)

    def test_normalize_url_rejects_path_only_input(self) -> None:
        kernel = ResearchKernel()
        normalized = kernel.normalize_url("/relative/path")
        self.assertEqual("", normalized)

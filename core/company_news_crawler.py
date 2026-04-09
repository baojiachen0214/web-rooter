"""
Company News Crawler - 公司新闻中心批量抓取器

将 web-rooter 专属模块整合为针对"低数量公司新闻重抓取"场景的完整执行器：

  - 任务调度：job_system.JobStore   — 每批次一个 job，实时写入 status/进度
  - 断点续爬：checkpoint.CheckpointManager — Ctrl+C 或崩溃后自动恢复
  - 流式进度：result_queue.ResultQueue    — 生产者写、消费者实时汇总
  - 内存保护：runtime_pressure + memory_optimizer — 自适应降级 + 批后清理
  - 元数据：  citation.build_web_citations — 每页附 source_url/timestamp/page_number
  - HTTP 优先，浏览器 fallback：aiohttp → playwright（可选依赖）

用法（命令行）::

    wr do-submit "批量抓取309家低数量公司新闻中心分页" \\
        --skill company_news_mining --crawl-pages=20

用法（Python API）::

    from pathlib import Path
    from core.company_news_crawler import CompanyRecord, run_batch

    companies = [
        CompanyRecord(name="示例科技", url="https://example.com", news_count_before=5),
        ...
    ]
    await run_batch(companies, output_dir=Path("0407stage2_archive"), max_pages=20)
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urljoin, urlparse, urlencode, urlunparse, parse_qs

from core.checkpoint import CheckpointManager
from core.citation import build_web_citations
from core.job_system import JobStore, get_job_store
from core.memory_optimizer import get_memory_optimizer
from core.result_queue import ResultQueue, StreamItem
from core.runtime_pressure import RuntimePressureController, RuntimePressurePolicy

try:
    import aiohttp
    _AIOHTTP_AVAILABLE = True
except ImportError:  # pragma: no cover
    _AIOHTTP_AVAILABLE = False

try:
    from playwright.async_api import async_playwright
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PLAYWRIGHT_AVAILABLE = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stealth User-Agent pool (mirrors config.StealthConfig.USER_AGENTS)
# ---------------------------------------------------------------------------
_USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CompanyRecord:
    """
    单家公司的基本信息，作为抓取任务的输入单元。

    Attributes:
        name: 公司名称（用于目录命名和日志）
        url:  公司官网 URL（新闻中心搜索的起点）
        news_count_before: 抓取前的新闻条数（从低数量公司清单读入）
        company_id: 可选的唯一标识；默认用 name 的安全化版本
    """
    name: str
    url: str
    news_count_before: int = 0
    company_id: str = ""

    def __post_init__(self) -> None:
        if not self.company_id:
            safe = re.sub(r"[^\w\u4e00-\u9fff-]", "_", self.name)
            self.company_id = safe[:64]


@dataclass
class PageCrawlResult:
    """
    单页抓取结果。

    Attributes:
        company_id:    所属公司 ID
        page_number:   页码（1-based）
        url:           实际抓取的 URL
        html:          原始 HTML（空字符串代表失败）
        news_links:    本页中提取到的新闻条目链接数量
        success:       是否成功
        via_browser:   是否经过浏览器 fallback
        error:         失败时的错误信息
        fetched_at:    UTC ISO 时间戳
    """
    company_id: str
    page_number: int
    url: str
    html: str = ""
    news_links: int = 0
    success: bool = False
    via_browser: bool = False
    error: Optional[str] = None
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Pagination URL discovery
# ---------------------------------------------------------------------------

# Patterns matched in order; first match wins per page.
_PAGE_PATTERNS: List[re.Pattern[str]] = [
    # ?page=N  or  &page=N
    re.compile(r"[?&]page=\d+", re.IGNORECASE),
    # /news/list/2  /news/2  /page/2
    re.compile(r"/(page|list|p)/(\d+)", re.IGNORECASE),
    # rel="next"
    re.compile(r'rel=["\']next["\']', re.IGNORECASE),
]


def _build_page_url(base_url: str, page: int) -> str:
    """
    从新闻列表首页 URL 推导第 N 页的 URL。

    策略（按优先级）：
    1. 如果 URL 中已有 ?page=\d+ 参数，替换页码。
    2. 如果 URL 路径符合 /list/N 或 /page/N 模式，替换数字段。
    3. 否则追加 ?page=N。
    """
    parsed = urlparse(base_url)

    # 策略 1：查询参数
    if re.search(r"(?:^|&)page=\d+", parsed.query, re.IGNORECASE):
        new_query = re.sub(r"(page=)\d+", rf"\g<1>{page}", parsed.query, flags=re.IGNORECASE)
        return urlunparse(parsed._replace(query=new_query))

    # 策略 2：路径段
    path_match = re.search(r"/(page|list|p)/(\d+)", parsed.path, re.IGNORECASE)
    if path_match:
        new_path = parsed.path[: path_match.start(2)] + str(page) + parsed.path[path_match.end(2):]
        return urlunparse(parsed._replace(path=new_path))

    # 策略 3：追加查询参数
    separator = "&" if parsed.query else "?"
    return base_url.rstrip("/") + f"{separator}page={page}"


def _extract_next_page_url(html: str, current_url: str) -> Optional[str]:
    """
    从 HTML 中提取 rel="next" 链接。若无则返回 None。
    """
    match = re.search(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*rel=["\']next["\']', html, re.IGNORECASE)
    if not match:
        match = re.search(r'rel=["\']next["\'][^>]*href=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if match:
        return urljoin(current_url, match.group(1))
    return None


def _count_news_links(html: str) -> int:
    """
    粗略统计页面中看似指向新闻详情页的链接数量。
    匹配规则：href 包含 /news/ | /article/ | /detail/ | /content/ 的 <a> 标签。
    """
    pattern = re.compile(r'<a\s[^>]*href=["\'][^"\']*(?:news|article|detail|content|info)[^"\']*["\']',
                          re.IGNORECASE)
    return len(pattern.findall(html))


# ---------------------------------------------------------------------------
# HTTP fetcher (aiohttp, stealth UA rotation)
# ---------------------------------------------------------------------------

async def _fetch_html_http(url: str, timeout: int = 20) -> tuple[int, str]:
    """
    使用 aiohttp 发起 HTTP 请求，随机轮换 User-Agent。

    Returns:
        (status_code, html_text)  — 失败时 status_code=-1, html_text=""
    """
    if not _AIOHTTP_AVAILABLE:
        return -1, ""
    ua = random.choice(_USER_AGENTS)
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.google.com/",
    }
    try:
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout),
                                   allow_redirects=True) as resp:
                status = resp.status
                if status == 200:
                    text = await resp.text(errors="replace")
                    return status, text
                return status, ""
    except Exception as exc:
        logger.debug("HTTP fetch failed %s: %s", url, exc)
        return -1, ""


# ---------------------------------------------------------------------------
# Browser fetcher (Playwright, optional)
# ---------------------------------------------------------------------------

async def _fetch_html_browser(url: str, timeout_ms: int = 20_000) -> tuple[int, str]:
    """
    使用 Playwright headless 浏览器抓取动态页面（HTTP fallback）。

    Returns:
        (200, html_text) on success, (-1, "") on failure.
    """
    if not _PLAYWRIGHT_AVAILABLE:
        logger.warning("Playwright not available; browser fallback disabled")
        return -1, ""
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=random.choice(_USER_AGENTS),
                locale="zh-CN",
                extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
            )
            page = await context.new_page()
            await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            html = await page.content()
            await browser.close()
            return 200, html
    except Exception as exc:
        logger.debug("Browser fetch failed %s: %s", url, exc)
        return -1, ""


# ---------------------------------------------------------------------------
# Core per-page fetcher (HTTP-first → browser fallback)
# ---------------------------------------------------------------------------

async def _fetch_page(
    url: str,
    allow_browser: bool = True,
    request_delay: float = 0.5,
) -> tuple[int, str, bool]:
    """
    Fetch a single URL.

    Returns:
        (status_code, html, via_browser)
    """
    await asyncio.sleep(request_delay)
    status, html = await _fetch_html_http(url)
    if status == 200 and html:
        return status, html, False

    # HTTP failed or returned non-200 — try browser if allowed
    if allow_browser:
        logger.debug("HTTP %s for %s — trying browser fallback", status, url)
        status, html = await _fetch_html_browser(url)
        if status == 200 and html:
            return status, html, True

    return status, html, False


# ---------------------------------------------------------------------------
# Per-company paginated crawl
# ---------------------------------------------------------------------------

async def crawl_news_pages(
    company_url: str,
    output_dir: Path,
    company_id: str,
    max_pages: int = 20,
    request_delay: float = 0.5,
    allow_browser: bool = True,
    pressure_controller: Optional[RuntimePressureController] = None,
) -> List[PageCrawlResult]:
    """
    对单家公司的新闻中心执行分页抓取，并将结果保存到本地。

    每页写入两个文件：
      - ``{output_dir}/{company_id}/page_{N:04d}.html``
      - ``{output_dir}/{company_id}/page_{N:04d}.meta.json``

    分页发现优先级：
    1. HTML 中的 rel="next" 链接
    2. 基于首页 URL 推导分页 URL（?page=N / /list/N / /page/N）

    Args:
        company_url:         新闻中心首页 URL
        output_dir:          输出根目录
        company_id:          公司唯一标识（用于子目录命名）
        max_pages:           最多抓取页数（默认 20）
        request_delay:       请求间隔秒数（礼貌延迟）
        allow_browser:       是否允许浏览器 fallback（由内存压力控制器动态关闭）
        pressure_controller: RuntimePressureController 实例（可选）

    Returns:
        List[PageCrawlResult] — 每页一条记录
    """
    company_dir = output_dir / company_id
    company_dir.mkdir(parents=True, exist_ok=True)

    results: List[PageCrawlResult] = []
    current_url: Optional[str] = company_url

    for page_num in range(1, max_pages + 1):
        if current_url is None:
            break

        # Adaptive limit from pressure controller
        if pressure_controller is not None:
            snapshot = pressure_controller.evaluate()
            limits = snapshot.get("limits", {})
            # At critical level, browser fallback is disabled
            effective_browser = allow_browser and limits.get("allow_browser_fallback", True)
            # Pause briefly under high/critical memory pressure
            if snapshot.get("level") in ("high", "critical"):
                logger.warning("Memory pressure %s — sleeping 5s before page %d",
                                snapshot["level"], page_num)
                await asyncio.sleep(5)
        else:
            effective_browser = allow_browser

        status, html, via_browser = await _fetch_page(
            current_url,
            allow_browser=effective_browser,
            request_delay=request_delay,
        )

        page_result = PageCrawlResult(
            company_id=company_id,
            page_number=page_num,
            url=current_url,
            html=html,
            news_links=_count_news_links(html) if html else 0,
            success=(status == 200 and bool(html)),
            via_browser=via_browser,
            error=None if (status == 200 and html) else f"http_status={status}",
        )
        results.append(page_result)

        if pressure_controller is not None:
            pressure_controller.record_outcome(page_result.success)

        # Save HTML
        html_path = company_dir / f"page_{page_num:04d}.html"
        html_path.write_text(html, encoding="utf-8", errors="replace")

        # Build citation metadata for this page
        fake_result = {
            "title": f"{company_id} 新闻列表 第{page_num}页",
            "url": current_url,
            "snippet": f"page={page_num} news_links={page_result.news_links}",
            "engine": "company_news_crawler",
            "rank": page_num,
        }
        citations = build_web_citations([fake_result], query=f"{company_id} 新闻中心", prefix="N")
        meta: Dict[str, Any] = {
            "company_id": company_id,
            "page_number": page_num,
            "url": current_url,
            "status_code": status,
            "news_links": page_result.news_links,
            "via_browser": via_browser,
            "success": page_result.success,
            "fetched_at": page_result.fetched_at,
            "citation": citations[0] if citations else {},
        }
        meta_path = company_dir / f"page_{page_num:04d}.meta.json"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        if not page_result.success:
            logger.warning("Page %d failed for %s (%s)", page_num, company_id, page_result.error)
            break

        # Discover next page URL
        next_url = _extract_next_page_url(html, current_url)
        if next_url and next_url != current_url:
            current_url = next_url
        elif page_num < max_pages:
            inferred = _build_page_url(company_url, page_num + 1)
            current_url = inferred
        else:
            current_url = None

    return results


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------

class CompanyNewsCrawler:
    """
    批量公司新闻抓取器。

    整合：
    - JobStore     → 批次级 job 跟踪（queued → running → completed/failed）
    - CheckpointManager → 每家公司完成后保存，支持 Ctrl+C 断点续爬
    - ResultQueue  → 实时流式进度（生产者写页面结果，消费者汇总统计）
    - RuntimePressureController → 自适应内存降级
    - MemoryOptimizer → 每批次结束后 cleanup

    Args:
        output_dir:    结果输出根目录
        max_pages:     每家公司最多抓取页数
        batch_size:    每批次处理的公司数（与 CheckpointManager 一致）
        request_delay: 请求间隔（秒）
        checkpoint_dir: 检查点存储目录（默认 output_dir/.checkpoints）
        job_store:     可注入的 JobStore（默认使用全局单例）
    """

    def __init__(
        self,
        output_dir: Path,
        max_pages: int = 20,
        batch_size: int = 50,
        request_delay: float = 0.5,
        checkpoint_dir: Optional[Path] = None,
        job_store: Optional[JobStore] = None,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_pages = max_pages
        self.batch_size = batch_size
        self.request_delay = request_delay

        _cp_dir = checkpoint_dir or (self.output_dir / ".checkpoints")
        self._checkpoint_mgr = CheckpointManager(
            spider_name="company_news_mining",
            checkpoint_dir=str(_cp_dir),
            max_checkpoints=10,
            auto_save_interval=60,
        )
        self._job_store: JobStore = job_store or get_job_store()
        self._pressure = RuntimePressureController(RuntimePressurePolicy())
        self._mem_opt = get_memory_optimizer()

    # ------------------------------------------------------------------
    # Resume support
    # ------------------------------------------------------------------

    def _load_completed_ids(self) -> set[str]:
        """从最近的检查点恢复已完成的公司 ID 集合。"""
        cp = self._checkpoint_mgr.load_checkpoint()
        if cp is None:
            return set()
        return set(cp.spider_state.get("completed_ids", []))

    def _save_checkpoint(self, completed_ids: set[str], stats: Dict[str, Any]) -> None:
        self._checkpoint_mgr.save_checkpoint(
            scheduler_state={"queue_size": 0},
            spider_state={"completed_ids": sorted(completed_ids)},
            stats=stats,
        )

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run(self, companies: Sequence[CompanyRecord]) -> Dict[str, Any]:
        """
        对给定的公司列表执行分页抓取。

        自动跳过已有检查点记录（completed）的公司，支持断点续爬。

        Args:
            companies: CompanyRecord 列表

        Returns:
            汇总统计字典（success_count, failed_count, total_pages, ...）
        """
        self._checkpoint_mgr.register_signal_handler()

        # Register this batch as a job
        job = self._job_store.create_do_job(
            task=f"company_news_mining: {len(companies)} companies",
            options={
                "max_pages": self.max_pages,
                "batch_size": self.batch_size,
                "output_dir": str(self.output_dir),
            },
            skill="company_news_mining",
            strict=False,
            source="company_news_crawler",
        )
        job_id = job["id"]
        self._job_store.update_job(job_id, status="running",
                                   started_at=datetime.now(timezone.utc).isoformat())
        logger.info("Job %s started — %d companies to process", job_id, len(companies))

        # Resume: skip already-completed companies
        completed_ids = self._load_completed_ids()
        pending = [c for c in companies if c.company_id not in completed_ids]
        skipped = len(companies) - len(pending)
        if skipped:
            logger.info("Resuming: skipped %d already-completed companies", skipped)

        # Result queue for streaming stats
        queue: ResultQueue = ResultQueue(maxsize=500, overflow_strategy="drop_oldest")

        # Statistics tracked by consumer
        stats: Dict[str, Any] = {
            "success_count": 0,
            "failed_count": 0,
            "total_pages": 0,
            "total_news_links": 0,
            "skipped_count": skipped,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

        async def _consume(item: StreamItem) -> None:
            """Progress consumer — accumulates stats from StreamItems."""
            d = item.data if isinstance(item.data, dict) else {}
            if item.is_error:
                stats["failed_count"] += 1
            elif item.is_item:
                stats["success_count"] += 1
                stats["total_pages"] += d.get("pages_fetched", 0)
                stats["total_news_links"] += d.get("total_news_links", 0)
            logger.info(
                "Progress — done: %d/%d | pages: %d | errors: %d",
                stats["success_count"] + stats["failed_count"],
                len(pending),
                stats["total_pages"],
                stats["failed_count"],
            )

        from core.result_queue import StreamConsumer
        consumer = StreamConsumer(queue)
        consumer.add_consumer(_consume, name="stats-consumer")

        # Process in batches
        try:
            for batch_start in range(0, len(pending), self.batch_size):
                if self._checkpoint_mgr.shutdown_requested:
                    logger.info("Shutdown requested — stopping after current batch")
                    break

                batch = pending[batch_start: batch_start + self.batch_size]
                batch_num = batch_start // self.batch_size + 1
                logger.info("Batch %d: processing %d companies", batch_num, len(batch))

                # Sequential within each company (respect request delay);
                # companies in a batch are processed one-by-one to keep
                # memory footprint predictable.
                for company in batch:
                    if self._checkpoint_mgr.shutdown_requested:
                        break
                    await self._process_company(company, queue, completed_ids, stats)

                # Cleanup memory after each batch
                self._mem_opt.clear_temp_results()
                self._pressure.clear()
                logger.info("Batch %d done — memory cleaned up", batch_num)

        except Exception as exc:
            logger.exception("Unexpected error in batch loop: %s", exc)
            self._job_store.update_job(job_id, status="failed", error=str(exc))
            raise
        finally:
            queue.close()
            await consumer.wait()
            stats["finished_at"] = datetime.now(timezone.utc).isoformat()
            self._save_checkpoint(completed_ids, stats)

        # Finalize job
        success = stats["failed_count"] == 0
        self._job_store.write_result(job_id, {"success": success, **stats})
        self._job_store.update_job(
            job_id,
            status="completed" if success else "failed",
            finished_at=stats["finished_at"],
            error=None if success else f"failed_companies={stats['failed_count']}",
        )
        logger.info(
            "Job %s finished — success=%d failed=%d pages=%d",
            job_id, stats["success_count"], stats["failed_count"], stats["total_pages"],
        )
        return stats

    async def _process_company(
        self,
        company: CompanyRecord,
        queue: ResultQueue,
        completed_ids: set[str],
        stats: Dict[str, Any],
    ) -> None:
        """处理单家公司：执行分页抓取并将结果写入 ResultQueue。"""
        logger.info("Processing company: %s (%s)", company.name, company.url)
        try:
            page_results = await crawl_news_pages(
                company_url=company.url,
                output_dir=self.output_dir,
                company_id=company.company_id,
                max_pages=self.max_pages,
                request_delay=self.request_delay,
                allow_browser=True,
                pressure_controller=self._pressure,
            )

            pages_fetched = sum(1 for r in page_results if r.success)
            total_news = sum(r.news_links for r in page_results)

            payload: Dict[str, Any] = {
                "company_id": company.company_id,
                "company_name": company.name,
                "news_count_before": company.news_count_before,
                "pages_fetched": pages_fetched,
                "total_news_links": total_news,
                "via_browser_count": sum(1 for r in page_results if r.via_browser),
            }

            # Write per-company summary (ensure directory exists even if crawl was mocked)
            summary_dir = self.output_dir / company.company_id
            summary_dir.mkdir(parents=True, exist_ok=True)
            summary_path = summary_dir / "crawl_summary.json"
            summary_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            completed_ids.add(company.company_id)
            self._save_checkpoint(completed_ids, stats)

            await queue.put(payload, item_type="item")

        except Exception as exc:
            logger.error("Failed to process %s: %s", company.name, exc)
            await queue.put(
                {"company_id": company.company_id, "error": str(exc)},
                item_type="error",
            )


# ---------------------------------------------------------------------------
# Quality verification
# ---------------------------------------------------------------------------

def build_verification_report(
    companies: Sequence[CompanyRecord],
    output_dir: Path,
) -> Dict[str, Any]:
    """
    读取每家公司的 crawl_summary.json，与 news_count_before 对比，
    生成质量验收报告。

    Args:
        companies:  原始公司列表（含 news_count_before）
        output_dir: 输出根目录（与抓取时相同）

    Returns:
        验收报告字典，包含 improved/unchanged/missing 三类公司。
    """
    improved: List[Dict[str, Any]] = []
    unchanged: List[Dict[str, Any]] = []
    missing: List[str] = []

    for company in companies:
        summary_path = output_dir / company.company_id / "crawl_summary.json"
        if not summary_path.exists():
            missing.append(company.company_id)
            continue
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            missing.append(company.company_id)
            continue

        after = summary.get("total_news_links", 0)
        before = company.news_count_before
        increase = after - before
        entry = {
            "company_id": company.company_id,
            "company_name": company.name,
            "news_count_before": before,
            "news_links_after": after,
            "increase": increase,
            "pages_fetched": summary.get("pages_fetched", 0),
        }
        if increase > 0:
            improved.append(entry)
        else:
            unchanged.append(entry)

    report: Dict[str, Any] = {
        "total": len(companies),
        "improved": len(improved),
        "unchanged": len(unchanged),
        "missing": len(missing),
        "improved_companies": improved,
        "unchanged_companies": unchanged,
        "missing_company_ids": missing,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    report_path = output_dir / "verification_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(
        "Verification — improved: %d, unchanged: %d, missing: %d",
        len(improved), len(unchanged), len(missing),
    )
    return report


# ---------------------------------------------------------------------------
# Public convenience entry point
# ---------------------------------------------------------------------------

async def run_batch(
    companies: Sequence[CompanyRecord],
    output_dir: Path,
    max_pages: int = 20,
    batch_size: int = 50,
    request_delay: float = 0.5,
    checkpoint_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    公共入口：批量抓取 + 最后自动生成验收报告。

    Returns:
        {"crawl_stats": ..., "verification": ...}
    """
    crawler = CompanyNewsCrawler(
        output_dir=output_dir,
        max_pages=max_pages,
        batch_size=batch_size,
        request_delay=request_delay,
        checkpoint_dir=checkpoint_dir,
    )
    crawl_stats = await crawler.run(companies)
    verification = build_verification_report(companies, output_dir)
    return {"crawl_stats": crawl_stats, "verification": verification}

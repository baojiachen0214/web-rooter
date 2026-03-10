"""
Web-Rooter - AI Web Crawling Agent
主入口文件
"""
import asyncio
import argparse
import json
import sys
import shlex
import shutil
import os
import subprocess
import importlib.util
from pathlib import Path
from typing import Optional, List
import logging

from agents.web_agent import WebAgent
from tools.mcp_tools import WebTools, run_mcp_server
from core.search.advanced import DeepSearchEngine, search_social_media, search_tech, search_commerce
from core.academic_search import AcademicSource

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 仅在显式开启时才切换 SelectorEventLoop（默认保持系统策略，避免影响 Playwright 子进程）。
if (
    sys.platform.startswith("win")
    and hasattr(asyncio, "WindowsSelectorEventLoopPolicy")
    and str(os.getenv("WEB_ROOTER_WINDOWS_SELECTOR_LOOP", "0")).strip().lower() in {"1", "true", "yes", "on"}
):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]
    except Exception:
        pass


class WebRooterCLI:
    """命令行界面"""

    def __init__(self):
        self.agent: Optional[WebAgent] = None
        self.tools: Optional[WebTools] = None

    async def start(self):
        """启动"""
        self.agent = WebAgent()
        await self.agent._init()
        print("[Web]  Web-Rooter 已启动")
        print("输入 'help' 查看可用命令")
        print()


    async def _ensure_tools(self):
        """按需初始化工具集，减少 CLI 冷启动开销。"""
        if self.tools is None:
            self.tools = WebTools()
            await self.tools.initialize()

    async def stop(self):
        """停止"""
        if self.agent:
            await self.agent.close()
        if self.tools:
            await self.tools.close()
        print("Bye 再见!")

    async def run_command(self, command: str, args: list[str]) -> bool:
        """运行命令"""
        if command == "visit" and args:
            url = args[0]
            use_browser = "--js" in args
            result = await self.agent.visit(url, use_browser=use_browser)
            self._print_result(result)

        elif command in {"quick", "q"} and args:
            # 忘记具体命令时的一键入口：URL -> visit，其他 -> web search
            use_browser = "--js" in args
            crawl_pages = 3
            input_parts = []
            i = 0
            while i < len(args):
                arg = args[i]
                if arg == "--js":
                    pass
                elif arg.startswith("--crawl-pages="):
                    crawl_pages = self._parse_option_int(arg.split("=", 1)[1], crawl_pages)
                elif arg.startswith("--crawl="):
                    crawl_pages = self._parse_option_int(arg.split("=", 1)[1], crawl_pages)
                elif arg == "--crawl-pages" and i + 1 < len(args):
                    i += 1
                    crawl_pages = self._parse_option_int(args[i], crawl_pages)
                elif arg == "--crawl" and i + 1 < len(args):
                    i += 1
                    crawl_pages = self._parse_option_int(args[i], crawl_pages)
                else:
                    input_parts.append(arg)
                i += 1

            raw_input = " ".join(input_parts).strip()
            if not raw_input:
                print("用法：quick <url|query> [--js] [--crawl-pages=N]")
                return True

            await self._run_inferred_input(
                raw_input,
                use_browser=use_browser,
                crawl_pages=crawl_pages,
            )

        elif command == "search" and args:
            url = None
            query_parts = []
            for arg in args:
                if url is None and arg.startswith(("http://", "https://")):
                    url = arg
                else:
                    query_parts.append(arg)

            query = " ".join(query_parts).strip()
            if not query:
                print("用法：search <query> [url]")
                return True

            result = await self.agent.search(query, url)
            self._print_result(result)

        elif command == "extract" and len(args) >= 2:
            url = args[0]
            target = " ".join(args[1:])
            result = await self.agent.extract(url, target)
            self._print_result(result)

        elif command == "crawl" and args:
            url = args[0]
            max_pages = 10
            max_depth = 3
            pattern = None
            allow_external = False
            allow_subdomains = True
            numeric_values = []
            i = 1

            while i < len(args):
                arg = args[i]
                if arg.startswith("--pages="):
                    max_pages = self._parse_option_int(arg.split("=", 1)[1], max_pages)
                elif arg.startswith("--depth="):
                    max_depth = self._parse_option_int(arg.split("=", 1)[1], max_depth)
                elif arg.startswith("--pattern="):
                    pattern = arg.split("=", 1)[1].strip() or None
                elif arg == "--pattern" and i + 1 < len(args):
                    i += 1
                    pattern = args[i].strip() or None
                elif arg == "--allow-external":
                    allow_external = True
                elif arg == "--no-subdomains":
                    allow_subdomains = False
                elif arg.isdigit():
                    numeric_values.append(int(arg))
                i += 1

            if numeric_values:
                max_pages = numeric_values[0]
            if len(numeric_values) > 1:
                max_depth = numeric_values[1]

            result = await self.agent.crawl(
                url,
                max_pages=max_pages,
                max_depth=max_depth,
                pattern=pattern,
                allow_external=allow_external,
                allow_subdomains=allow_subdomains,
            )
            self._print_result(result)

        elif command == "links" and args:
            await self._ensure_tools()
            url = args[0]
            internal_only = "--all" not in args
            result = await self.tools.get_links(url, internal_only=internal_only)
            self._print_result(result)

        elif command == "kb" or command == "knowledge":
            await self._ensure_tools()
            result = await self.tools.get_knowledge_base()
            self._print_result(result)

        elif command == "fetch" and args:
            await self._ensure_tools()
            url = args[0]
            result = await self.tools.fetch(url)
            self._print_result(result)

        elif command == "web" and args:
            auto_crawl = True
            crawl_pages = 3
            query_parts = []
            i = 0

            while i < len(args):
                arg = args[i]
                if arg == "--no-crawl":
                    auto_crawl = False
                elif arg.startswith("--crawl-pages="):
                    crawl_pages = self._parse_option_int(arg.split("=", 1)[1], crawl_pages)
                elif arg.startswith("--crawl="):
                    crawl_pages = self._parse_option_int(arg.split("=", 1)[1], crawl_pages)
                elif arg == "--crawl-pages" and i + 1 < len(args):
                    i += 1
                    crawl_pages = self._parse_option_int(args[i], crawl_pages)
                elif arg == "--crawl" and i + 1 < len(args):
                    i += 1
                    crawl_pages = self._parse_option_int(args[i], crawl_pages)
                else:
                    query_parts.append(arg)
                i += 1

            query = " ".join(query_parts).strip()
            if not query:
                print("用法：web <query> [--no-crawl] [--crawl-pages=N]")
                return True

            result = await self.agent.search_internet(
                query,
                auto_crawl=auto_crawl,
                crawl_pages=crawl_pages,
            )
            self._print_result(result)

        elif command == "research" and args:
            topic = " ".join(args)
            result = await self.agent.research_topic(topic)
            self._print_result(result)

        elif command in {"mindsearch", "ms"} and args:
            use_en = False
            crawl = 1
            turns = 3
            branches = 4
            num_results = 8
            planner_name: Optional[str] = None
            strict_expand: Optional[bool] = None
            channel_profiles: List[str] = []
            query_parts = []
            i = 0
            while i < len(args):
                arg = args[i]
                if arg in {"--en", "--english"}:
                    use_en = True
                elif arg.startswith("--crawl="):
                    crawl = self._parse_option_int(arg.split("=", 1)[1], crawl)
                elif arg == "--crawl" and i + 1 < len(args):
                    i += 1
                    crawl = self._parse_option_int(args[i], crawl)
                elif arg.startswith("--turns="):
                    turns = self._parse_option_int(arg.split("=", 1)[1], turns)
                elif arg == "--turns" and i + 1 < len(args):
                    i += 1
                    turns = self._parse_option_int(args[i], turns)
                elif arg.startswith("--branches="):
                    branches = self._parse_option_int(arg.split("=", 1)[1], branches)
                elif arg == "--branches" and i + 1 < len(args):
                    i += 1
                    branches = self._parse_option_int(args[i], branches)
                elif arg.startswith("--num-results="):
                    num_results = self._parse_option_int(arg.split("=", 1)[1], num_results)
                elif arg == "--num-results" and i + 1 < len(args):
                    i += 1
                    num_results = self._parse_option_int(args[i], num_results)
                elif arg.startswith("--planner="):
                    planner_name = arg.split("=", 1)[1].strip() or None
                elif arg == "--planner" and i + 1 < len(args):
                    i += 1
                    planner_name = args[i].strip() or None
                elif arg == "--strict-expand":
                    strict_expand = True
                elif arg == "--no-strict-expand":
                    strict_expand = False
                elif arg == "--news":
                    channel_profiles.append("news")
                elif arg in {"--platform", "--platforms"}:
                    channel_profiles.append("platforms")
                elif arg in {"--commerce", "--shopping"}:
                    channel_profiles.append("commerce")
                elif arg.startswith("--channel="):
                    channel_profiles.extend([x.strip() for x in arg.split("=", 1)[1].split(",") if x.strip()])
                elif arg == "--channel" and i + 1 < len(args):
                    i += 1
                    channel_profiles.extend([x.strip() for x in args[i].split(",") if x.strip()])
                else:
                    query_parts.append(arg)
                i += 1

            query = " ".join(query_parts).strip()
            if not query:
                print("用法：mindsearch <query> [--turns=N] [--branches=N] [--num-results=N] [--crawl=N] [--en] [--planner=name] [--strict-expand] [--news|--platforms|--commerce|--channel=x,y]")
                return True

            result = await self.agent.mindsearch_research(
                query=query,
                max_turns=turns,
                max_branches=branches,
                num_results=num_results,
                crawl_top=crawl,
                use_english=use_en,
                channel_profiles=channel_profiles or None,
                planner_name=planner_name,
                strict_expand=strict_expand,
            )
            self._print_result(result)

        elif command == "context":
            limit = 20
            event_type = None
            i = 0
            while i < len(args):
                arg = args[i]
                if arg.startswith("--limit="):
                    limit = self._parse_option_int(arg.split("=", 1)[1], limit)
                elif arg == "--limit" and i + 1 < len(args):
                    i += 1
                    limit = self._parse_option_int(args[i], limit)
                elif arg.startswith("--event="):
                    event_type = arg.split("=", 1)[1].strip() or None
                elif arg == "--event" and i + 1 < len(args):
                    i += 1
                    event_type = args[i].strip() or None
                i += 1

            snapshot = self.agent.get_global_context_snapshot(limit=limit, event_type=event_type)
            self._print_result({"success": True, "context": snapshot})

        elif command in {"processors", "postprocessors"}:
            specs: List[str] = []
            force = False
            i = 0
            while i < len(args):
                arg = args[i]
                if arg.startswith("--load="):
                    specs.extend([x.strip() for x in arg.split("=", 1)[1].split(",") if x.strip()])
                elif arg == "--load" and i + 1 < len(args):
                    i += 1
                    specs.extend([x.strip() for x in args[i].split(",") if x.strip()])
                elif arg == "--force":
                    force = True
                i += 1

            data = self.agent.register_post_processors(specs=specs or None, force=force)
            self._print_result({"success": True, **data})

        elif command in {"planners", "planner"}:
            specs: List[str] = []
            force = False
            i = 0
            while i < len(args):
                arg = args[i]
                if arg.startswith("--load="):
                    specs.extend([x.strip() for x in arg.split("=", 1)[1].split(",") if x.strip()])
                elif arg == "--load" and i + 1 < len(args):
                    i += 1
                    specs.extend([x.strip() for x in args[i].split(",") if x.strip()])
                elif arg == "--force":
                    force = True
                i += 1

            data = self.agent.register_research_planners(specs=specs or None, force=force)
            self._print_result({"success": True, **data})

        elif command in {"challenge-profiles", "challenge_profiles", "challenges"}:
            data = self.agent.get_challenge_profiles()
            self._print_result({"success": True, **data})

        elif command == "academic" and args:
            include_code = True
            fetch_abstracts = True
            num_results = 12
            sources: List[AcademicSource] = []
            query_parts = []
            source_map = {
                "arxiv": AcademicSource.ARXIV,
                "google_scholar": AcademicSource.GOOGLE_SCHOLAR,
                "scholar": AcademicSource.GOOGLE_SCHOLAR,
                "semantic_scholar": AcademicSource.SEMANTIC_SCHOLAR,
                "semantic": AcademicSource.SEMANTIC_SCHOLAR,
                "pubmed": AcademicSource.PUBMED,
                "ieee": AcademicSource.IEEE,
                "cnki": AcademicSource.CNKI,
                "wanfang": AcademicSource.WANFANG,
                "paper_with_code": AcademicSource.PAPER_WITH_CODE,
                "pwc": AcademicSource.PAPER_WITH_CODE,
                "github": AcademicSource.GITHUB,
                "gitee": AcademicSource.GITEE,
            }

            i = 0
            while i < len(args):
                arg = args[i]
                if arg == "--papers-only":
                    include_code = False
                elif arg == "--with-code":
                    include_code = True
                elif arg == "--no-abstracts":
                    fetch_abstracts = False
                elif arg.startswith("--num-results="):
                    num_results = self._parse_option_int(arg.split("=", 1)[1], num_results)
                elif arg == "--num-results" and i + 1 < len(args):
                    i += 1
                    num_results = self._parse_option_int(args[i], num_results)
                elif arg.startswith("--source="):
                    source_key = arg.split("=", 1)[1].strip().lower()
                    source_enum = source_map.get(source_key)
                    if source_enum and source_enum not in sources:
                        sources.append(source_enum)
                elif arg == "--source" and i + 1 < len(args):
                    i += 1
                    source_key = args[i].strip().lower()
                    source_enum = source_map.get(source_key)
                    if source_enum and source_enum not in sources:
                        sources.append(source_enum)
                else:
                    query_parts.append(arg)
                i += 1

            query = " ".join(query_parts).strip()
            if not query:
                print("用法：academic <query> [--papers-only|--with-code] [--no-abstracts] [--num-results=N] [--source=arxiv]")
                return True

            result = await self.agent.search_academic(
                query,
                sources=sources or None,
                num_results=num_results,
                include_code=include_code,
                fetch_abstracts=fetch_abstracts,
            )
            self._print_result(result)

        elif command == "site" and len(args) >= 2:
            url = args[0]
            query = " ".join(args[1:])
            result = await self.agent.search_with_form(url, query)
            self._print_result(result)

        elif command == "deep" or command == "deepsearch":
            use_en = False
            crawl = 0
            num_results = 10
            query_variants = 1
            channel_profiles: List[str] = []
            query_parts = []
            i = 0

            while i < len(args):
                arg = args[i]
                if arg in {"--en", "--english"}:
                    use_en = True
                elif arg == "--news":
                    channel_profiles.append("news")
                elif arg in {"--platform", "--platforms"}:
                    channel_profiles.append("platforms")
                elif arg in {"--commerce", "--shopping"}:
                    channel_profiles.append("commerce")
                elif arg.startswith("--channel="):
                    raw = arg.split("=", 1)[1]
                    channel_profiles.extend([x.strip() for x in raw.split(",") if x.strip()])
                elif arg == "--channel" and i + 1 < len(args):
                    i += 1
                    channel_profiles.extend([x.strip() for x in args[i].split(",") if x.strip()])
                elif arg.startswith("--crawl="):
                    crawl = self._parse_option_int(arg.split("=", 1)[1], crawl)
                elif arg == "--crawl" and i + 1 < len(args):
                    i += 1
                    crawl = self._parse_option_int(args[i], crawl)
                elif arg.startswith("--num-results="):
                    num_results = self._parse_option_int(arg.split("=", 1)[1], num_results)
                elif arg == "--num-results" and i + 1 < len(args):
                    i += 1
                    num_results = self._parse_option_int(args[i], num_results)
                elif arg.startswith("--variants="):
                    query_variants = self._parse_option_int(arg.split("=", 1)[1], query_variants)
                elif arg.startswith("--query-variants="):
                    query_variants = self._parse_option_int(arg.split("=", 1)[1], query_variants)
                elif arg in {"--variants", "--query-variants"} and i + 1 < len(args):
                    i += 1
                    query_variants = self._parse_option_int(args[i], query_variants)
                elif arg.isdigit() and i == len(args) - 1:
                    crawl = self._parse_option_int(arg, crawl)
                else:
                    query_parts.append(arg)
                i += 1

            query = " ".join(query_parts).strip()
            if not query:
                print("用法：deep <query> [--en] [--crawl=N] [--num-results=N] [--variants=N] [--news] [--platforms] [--commerce] [--channel=x,y]")
                return True

            logger.info(
                "执行深度搜索：%s, 英文搜索：%s, 爬取前%s个结果, 渠道=%s",
                query,
                use_en,
                crawl,
                ",".join(channel_profiles) if channel_profiles else "default",
            )
            deep_search = DeepSearchEngine()
            try:
                result = await deep_search.deep_search(
                    query,
                    num_results=num_results,
                    use_english=use_en,
                    crawl_top=crawl,
                    query_variants=query_variants,
                    channel_profiles=channel_profiles or None,
                )
            finally:
                await deep_search.close()
            self._print_result(result)

        elif command == "social":
            platforms = []
            query_parts = []
            supported_platforms = {
                "xiaohongshu", "xhs",
                "zhihu",
                "tieba",
                "douyin",
                "bilibili", "bili",
                "weibo",
                "reddit",
                "twitter", "x",
            }

            for arg in args:
                if arg.startswith("--platform="):
                    platforms.append(arg.split("=", 1)[1])
                elif arg in supported_platforms:
                    platforms.append(arg)
                else:
                    query_parts.append(arg)

            query = " ".join(query_parts).strip()
            if not query:
                print("用法：social <query> [--platform=xiaohongshu|zhihu|tieba|douyin|bilibili|weibo|reddit|twitter]")
                return True

            logger.info(f"搜索社交媒体：{query}, 平台：{platforms or '全部'}")
            result = await search_social_media(query, platforms or None)
            self._print_result(result)

        elif command in {"shopping", "shop", "commerce"}:
            platforms = []
            query_parts = []
            supported_platforms = {
                "taobao", "tmall",
                "jd", "jingdong",
                "pinduoduo", "pdd",
                "meituan", "dianping",
            }

            for arg in args:
                if arg.startswith("--platform="):
                    platforms.append(arg.split("=", 1)[1])
                elif arg in supported_platforms:
                    platforms.append(arg)
                else:
                    query_parts.append(arg)

            query = " ".join(query_parts).strip()
            if not query:
                print("用法：shopping <query> [--platform=taobao|jd|pinduoduo|meituan]")
                return True

            logger.info(f"搜索电商平台：{query}, 平台：{platforms or '全部'}")
            result = await search_commerce(query, platforms or None)
            self._print_result(result)

        elif command == "tech":
            sources = []
            query_parts = []
            supported_sources = {"github", "stackoverflow", "medium", "hackernews"}

            for arg in args:
                if arg.startswith("--source="):
                    sources.append(arg.split("=", 1)[1])
                elif arg in supported_sources:
                    sources.append(arg)
                else:
                    query_parts.append(arg)

            query = " ".join(query_parts).strip()
            if not query:
                print("用法：tech <query> [--source=github] [--source=stackoverflow]")
                return True

            logger.info(f"搜索技术内容：{query}, 来源：{sources or '全部'}")
            result = await search_tech(query, sources or None)
            self._print_result(result)

        elif command == "export":
            if len(args) < 2:
                print("用法：export <query> <output_file>")
                print("示例：export AI 新闻 output.json")
            else:
                query = " ".join(args[:-1]).strip()
                output_file = args[-1]
                if not query:
                    print("Error: 查询词不能为空")
                    return True

                deep_search = DeepSearchEngine()
                try:
                    result = await deep_search.deep_search(
                        query,
                        num_results=20,
                        use_english=True,
                        crawl_top=5,
                    )
                finally:
                    await deep_search.close()

                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                print(f"结果已导出到：{output_file}")
                print(f"共 {result['total_results']} 条结果")

        elif command == "doctor":
            await self._run_doctor()

        elif command == "help":
            self._print_help()

        elif command == "quit" or command == "exit":
            return False

        else:
            if self._looks_like_url(command):
                use_browser = "--js" in args
                url_parts = [command] + [a for a in args if not a.startswith("--")]
                url = " ".join(url_parts).strip()
                print(f"[提示] 未识别命令 '{command}'，检测为 URL，按 visit 执行。")
                await self._run_inferred_input(url, use_browser=use_browser)
            else:
                crawl_pages = 3
                query_parts = []
                i = 0
                while i < len(args):
                    arg = args[i]
                    if arg.startswith("--crawl-pages="):
                        crawl_pages = self._parse_option_int(arg.split("=", 1)[1], crawl_pages)
                    elif arg.startswith("--crawl="):
                        crawl_pages = self._parse_option_int(arg.split("=", 1)[1], crawl_pages)
                    elif arg == "--crawl-pages" and i + 1 < len(args):
                        i += 1
                        crawl_pages = self._parse_option_int(args[i], crawl_pages)
                    elif arg == "--crawl" and i + 1 < len(args):
                        i += 1
                        crawl_pages = self._parse_option_int(args[i], crawl_pages)
                    elif not arg.startswith("--"):
                        query_parts.append(arg)
                    i += 1

                inferred_input = " ".join([command] + query_parts).strip()
                if inferred_input:
                    print(f"[提示] 未识别命令 '{command}'，按智能模式执行。")
                    await self._run_inferred_input(inferred_input, crawl_pages=crawl_pages)
                else:
                    print(f"Error: 未知命令：{command}")
                    print("输入 'help' 查看可用命令")
                    return True

        return True

    async def _run_inferred_input(
        self,
        raw_input: str,
        use_browser: bool = False,
        crawl_pages: int = 3,
    ):
        """根据输入自动判定执行 visit 或 web 搜索。"""
        if self._looks_like_url(raw_input):
            result = await self.agent.visit(raw_input, use_browser=use_browser)
        else:
            result = await self.agent.search_internet(
                raw_input,
                auto_crawl=True,
                crawl_pages=max(0, crawl_pages),
            )
        self._print_result(result)

    @staticmethod
    def _looks_like_url(text: str) -> bool:
        value = text.strip().lower()
        return value.startswith(("http://", "https://", "www."))

    @staticmethod
    def _parse_option_int(value: str, default: int) -> int:
        """安全解析整数参数。"""
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    async def _run_doctor(self):
        """运行本地环境诊断，减少 CLI 集成的试错成本。"""
        print("=" * 60)
        print("Web-Rooter Doctor")
        print("=" * 60)

        checks = []

        def add_check(name: str, ok: bool, detail: str, fix: Optional[str] = None):
            checks.append(ok)
            marker = "OK" if ok else "FAIL"
            print(f"[{marker}] {name}: {detail}")
            if fix and not ok:
                print(f"      修复建议: {fix}")

        def short_error(exc: Exception) -> str:
            message = str(exc).strip()
            if message:
                return message.splitlines()[0]
            return exc.__class__.__name__

        def detect_local_recommended_python() -> Optional[str]:
            candidates: List[Path] = []
            if sys.platform.startswith("win"):
                candidates.extend(
                    [
                        Path.cwd() / ".venv312" / "Scripts" / "python.exe",
                        Path.cwd() / ".venv" / "Scripts" / "python.exe",
                    ]
                )
            else:
                candidates.extend(
                    [
                        Path.cwd() / ".venv312" / "bin" / "python",
                        Path.cwd() / ".venv" / "bin" / "python",
                    ]
                )

            for candidate in candidates:
                if not candidate.exists():
                    continue
                try:
                    probe = subprocess.run(
                        [str(candidate), "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if probe.returncode != 0:
                        continue
                    version_text = (probe.stdout or "").strip()
                    major, minor = version_text.split(".", 1)
                    if (int(major), int(minor)) >= (3, 10):
                        return str(candidate)
                except Exception:
                    continue
            return None

        recommended_python = detect_local_recommended_python()

        python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        add_check(
            "Python",
            sys.version_info >= (3, 10),
            f"{python_version} ({sys.executable})",
            (
                f"请升级到 Python 3.10+，或改用: {recommended_python} main.py --doctor"
                if recommended_python
                else "请升级到 Python 3.10 或更高版本"
            ),
        )

        for module_name in ("aiohttp", "playwright", "mcp"):
            installed = importlib.util.find_spec(module_name) is not None
            add_check(
                f"依赖模块: {module_name}",
                installed,
                "已安装" if installed else "未安装",
                (
                    f"执行: {recommended_python} -m pip install {module_name}"
                    if recommended_python
                    else f"执行: pip install {module_name}"
                ),
            )

        playwright_cli = shutil.which("playwright")
        if playwright_cli is None:
            for bin_name in ("playwright.exe", "playwright.cmd", "playwright"):
                candidate = Path(sys.executable).with_name(bin_name)
                if candidate.exists():
                    playwright_cli = str(candidate)
                    break
        if playwright_cli is None:
            try:
                probe = subprocess.run(
                    [sys.executable, "-m", "playwright", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
                if probe.returncode == 0:
                    playwright_cli = f"{sys.executable} -m playwright"
            except Exception:
                playwright_cli = None
        add_check(
            "Playwright CLI",
            playwright_cli is not None,
            playwright_cli or "未找到",
            "执行: python -m playwright install chromium",
        )

        if sys.platform.startswith("win"):
            browser_cache_dir = Path.home() / "AppData" / "Local" / "ms-playwright"
        elif sys.platform == "darwin":
            browser_cache_dir = Path.home() / "Library" / "Caches" / "ms-playwright"
        else:
            browser_cache_dir = Path.home() / ".cache" / "ms-playwright"

        chromium_installs = list(browser_cache_dir.glob("chromium-*")) if browser_cache_dir.exists() else []
        add_check(
            "浏览器运行时",
            len(chromium_installs) > 0,
            f"检测到 {len(chromium_installs)} 个 Chromium 安装" if chromium_installs else f"未检测到浏览器缓存目录: {browser_cache_dir}",
            "执行: playwright install chromium",
        )

        try:
            http_result = await asyncio.wait_for(
                self.agent._crawler.fetch("https://example.com", use_proxy=False, use_cache=False),
                timeout=12,
            )
            add_check(
                "HTTP 抓取链路",
                http_result.success,
                f"status={http_result.status_code}" if http_result.success else (http_result.error or f"status={http_result.status_code}"),
                "网络受限时优先使用 visit <url> --js",
            )
        except Exception as e:
            add_check(
                "HTTP 抓取链路",
                False,
                short_error(e),
                "检查网络连接，或使用 visit <url> --js",
            )

        success_count = sum(1 for ok in checks if ok)
        print("-" * 60)
        print(f"诊断结果: {success_count}/{len(checks)} 通过")
        if success_count != len(checks):
            print("建议先完成 FAIL 项，再执行深度抓取任务。")
        print("=" * 60)

    def _print_result(self, result):
        """打印结果"""
        if hasattr(result, "to_dict"):
            result = result.to_dict()

        if isinstance(result, dict):
            max_chars = self._parse_option_int(os.environ.get("WEB_ROOTER_MAX_OUTPUT_CHARS", "30000"), 30000)
            render_target = result

            # 优先保留 citations / comparison，必要时压缩 crawled_content 正文以减少输出噪音。
            crawled = result.get("crawled_content")
            if isinstance(crawled, list) and crawled:
                compact_crawled = []
                for item in crawled[:8]:
                    if isinstance(item, dict):
                        compact_item = dict(item)
                        if isinstance(compact_item.get("content"), str):
                            compact_item["content"] = compact_item["content"][:800]
                        compact_crawled.append(compact_item)
                render_target = dict(result)
                render_target["crawled_content"] = compact_crawled

            rendered = json.dumps(render_target, ensure_ascii=False, indent=2)
            if len(rendered) > max_chars:
                rendered = rendered[:max_chars] + "\n... [truncated]"
            print(rendered)
        else:
            print(result)

    def _print_help(self):
        """打印帮助"""
        help_text = """
Web-Rooter 可用命令:

【网页访问】
  visit <url> [--js]              - 访问网页 (--js 使用浏览器)
  quick <url|query> [--js]        - 智能入口（URL 自动 visit，关键词自动 web）
  search <query> [url]            - 在已访问页面中搜索
  extract <url> <target>          - 提取特定信息
  crawl <url> [pages] [depth] [--pattern=REGEX] [--allow-external] [--no-subdomains]
  links <url> [--all]             - 获取链接
  kb / knowledge                  - 查看知识库
  fetch <url>                     - 获取页面

【互联网搜索】
  web <query> [--no-crawl] [--crawl-pages=N]
  deep <query> [--en] [--crawl=N] [--num-results=N] [--variants=N] [--news] [--platforms] [--commerce] [--channel=x,y]
  research <topic>                - 深度研究主题
  mindsearch <query> [--turns=N] [--branches=N] [--num-results=N] [--crawl=N] [--en] [--planner=name] [--strict-expand] [--channel=x,y]

【垂直搜索】
  social <query> [--platform=xxx] - 平台：xiaohongshu/zhihu/tieba/douyin/bilibili/weibo/reddit/twitter
  shopping <query> [--platform=xxx] - 平台：taobao/jd/pinduoduo/meituan
  tech <query> [--source=xxx]     - 来源：github/stackoverflow/medium/hackernews
  academic <query> [--papers-only|--with-code] [--no-abstracts] [--num-results=N] [--source=xxx]
  site <url> <query>              - 在网站内搜索

【导出与诊断】
  export <query> <file>           - 导出深度搜索结果到 JSON
  doctor                          - 环境自检（依赖/浏览器/抓取链路）
  context [--limit=N] [--event=type] - 查看全局深度抓取上下文事件
  processors [--load=module:obj] [--force] - 查看/加载抓取后处理扩展
  planners [--load=module:obj] [--force] - 查看/加载 MindSearch planner 扩展
  challenge-profiles              - 查看 challenge workflow 路由档案

【其他】
  help                            - 帮助信息
  quit / exit                     - 退出

示例:
  visit https://example.com
  quick https://example.com --js
  quick "WorldQuant alpha101 因子"
  web AI 大模型 --no-crawl
  web AI 大模型 --crawl-pages=5
  deep "苹果发布会" --en --crawl=5 --num-results=20 --variants=3 --news
  deep "护肤品评测" --commerce
  deep "AI Agent 工程化" --platforms --channel=news,commerce
  mindsearch "多模态大模型 工程落地" --turns=3 --branches=4 --crawl=1 --planner=heuristic --strict-expand --channel=news,platforms
  crawl https://docs.python.org 20 2 --pattern="/3/library/" --no-subdomains
  social "iPhone 17" --platform=xiaohongshu --platform=zhihu --platform=douyin
  shopping "羽绒服 轻量" --platform=taobao --platform=jd
  tech "transformer" --source=github
  academic Transformer --papers-only --source=arxiv --source=semantic_scholar
  academic "RAG evaluation" --with-code --num-results=15 --source=github
  export "AI 新闻" ai_news.json
  context --limit=30
  processors --load=plugins/post_processors/my_proc.py:create_processor --force
  planners --load=plugins/planners/my_planner.py:create_planner --force
  challenge-profiles
  doctor
  # 也可直接输入 URL 或查询词（未知命令会自动转智能模式）
  python main.py "https://example.com"
  python main.py "量化交易 因子 最新讨论"
"""
        print(help_text)


async def interactive_mode():
    """交互模式"""
    cli = WebRooterCLI()
    await cli.start()

    try:
        while True:
            try:
                user_input = input("> web-rooter> ").strip()
            except EOFError:
                break

            if not user_input:
                continue

            try:
                parts = shlex.split(user_input)
            except ValueError as e:
                print(f"Error: 命令解析失败 - {e}")
                continue

            command = parts[0]
            args = parts[1:]

            should_continue = await cli.run_command(command, args)
            if not should_continue:
                break

    finally:
        await cli.stop()


async def command_mode(command: str, args: list[str]):
    """命令行模式"""
    cli = WebRooterCLI()
    await cli.start()

    try:
        await cli.run_command(command, args)
    finally:
        await cli.stop()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="[Web]  Web-Rooter - AI Web Crawling Agent"
    )

    parser.add_argument(
        "--mcp",
        action="store_true",
        help="运行 MCP 服务器"
    )

    parser.add_argument(
        "--server",
        action="store_true",
        help="运行 HTTP 服务器"
    )

    parser.add_argument(
        "--doctor",
        action="store_true",
        help="运行环境自检"
    )

    parser.add_argument(
        "command",
        nargs="?",
        help="要执行的命令"
    )

    parser.add_argument(
        "args",
        nargs="*",
        help="命令参数"
    )

    args, unknown = parser.parse_known_args()
    if unknown:
        args.args.extend(unknown)

    if args.mcp:
        print("[MCP] 启动 MCP 服务器...")
        asyncio.run(run_mcp_server())
    elif args.server:
        print("[API] 启动 HTTP 服务器...")
        from server import run_http_server
        asyncio.run(run_http_server())
    elif args.doctor:
        asyncio.run(command_mode("doctor", []))
    elif args.command:
        asyncio.run(command_mode(args.command, args.args))
    else:
        asyncio.run(interactive_mode())


if __name__ == "__main__":
    main()

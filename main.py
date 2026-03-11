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
import difflib
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
import logging

from agents.web_agent import WebAgent
from tools.mcp_tools import WebTools, run_mcp_server
from core.search.advanced import (
    DeepSearchEngine,
    AdvancedSearchEngine,
    search_social_media,
    search_tech,
    search_commerce,
)
from core.academic_search import AcademicSource
from core.command_ir import build_command_ir, lint_command_ir, summarize_lint, has_lint_errors
from core.safe_mode import get_safe_mode_manager, evaluate_safe_mode_command
from core.job_system import get_job_store, spawn_job_worker

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
    _KNOWN_COMMAND_ALIASES = {
        "visit",
        "html",
        "dom",
        "do",
        "do-plan",
        "do_plan",
        "plan",
        "do-submit",
        "do_submit",
        "jobs",
        "job-status",
        "job_status",
        "job-result",
        "job_result",
        "job-worker",
        "job_worker",
        "quick",
        "q",
        "task",
        "orchestrate",
        "auto",
        "search",
        "extract",
        "crawl",
        "links",
        "kb",
        "knowledge",
        "fetch",
        "web",
        "research",
        "mindsearch",
        "ms",
        "context",
        "processors",
        "postprocessors",
        "planners",
        "planner",
        "challenge-profiles",
        "challenge_profiles",
        "challenges",
        "auth-profiles",
        "auth_profiles",
        "login-profiles",
        "login_profiles",
        "auth-hint",
        "auth_hint",
        "login-hint",
        "login_hint",
        "auth-template",
        "auth_template",
        "login-template",
        "login_template",
        "workflow-schema",
        "workflow_schema",
        "flow-schema",
        "flow_schema",
        "workflow-template",
        "workflow_template",
        "flow-template",
        "flow_template",
        "workflow",
        "flow",
        "skills",
        "skill-profiles",
        "skill_profiles",
        "ir-lint",
        "ir_lint",
        "lint-ir",
        "lint_ir",
        "academic",
        "site",
        "deep",
        "deepsearch",
        "social",
        "shopping",
        "shop",
        "commerce",
        "tech",
        "export",
        "doctor",
        "help",
        "quit",
        "exit",
        "safe-mode",
        "safe_mode",
        "guard",
    }

    def __init__(self):
        self.agent: Optional[WebAgent] = None
        self.tools: Optional[WebTools] = None
        self._safe_mode = get_safe_mode_manager()
        self._job_store = get_job_store()

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
        if command in {"safe-mode", "safe_mode", "guard"}:
            payload = self._handle_safe_mode_command(args)
            self._print_result(payload)
            return True

        guard = self._evaluate_safe_mode_guard(command, args)
        if not guard.get("allowed", True):
            self._print_result(
                {
                    "success": False,
                    "error": "safe_mode_blocked",
                    "guard": guard,
                }
            )
            return True

        if command == "visit" and args:
            url = args[0]
            use_browser = "--js" in args
            result = await self.agent.visit(url, use_browser=use_browser)
            self._print_result(result)

        elif command in {"html", "dom"} and args:
            url = args[0]
            use_browser = "--js" in args
            auto_fallback = "--no-fallback" not in args
            max_chars = 80000
            i = 1
            while i < len(args):
                arg = args[i]
                if arg.startswith("--max-chars="):
                    max_chars = self._parse_option_int(arg.split("=", 1)[1], max_chars)
                elif arg == "--max-chars" and i + 1 < len(args):
                    i += 1
                    max_chars = self._parse_option_int(args[i], max_chars)
                i += 1
            result = await self.agent.fetch_html(
                url=url,
                use_browser=use_browser,
                auto_fallback=auto_fallback,
                max_chars=max_chars,
            )
            self._print_result(result)

        elif command in {"do"}:
            # CLI 单入口：先编译 IR + lint，再执行 workflow。
            task_parts: List[str] = []
            explicit_skill: Optional[str] = None
            use_browser: Optional[bool] = None
            html_first: Optional[bool] = None
            crawl_assist: Optional[bool] = None
            top_results: Optional[int] = None
            crawl_pages: Optional[int] = None
            strict = False
            dry_run = False

            i = 0
            while i < len(args):
                arg = args[i]
                if arg == "--strict":
                    strict = True
                elif arg == "--dry-run":
                    dry_run = True
                elif arg == "--js":
                    use_browser = True
                elif arg == "--no-js":
                    use_browser = False
                elif arg == "--crawl-assist":
                    crawl_assist = True
                elif arg == "--no-crawl-assist":
                    crawl_assist = False
                elif arg == "--html-first":
                    html_first = True
                elif arg == "--no-html-first":
                    html_first = False
                elif arg.startswith("--top="):
                    top_results = self._parse_option_int(arg.split("=", 1)[1], 5)
                elif arg == "--top" and i + 1 < len(args):
                    i += 1
                    top_results = self._parse_option_int(args[i], 5)
                elif arg.startswith("--crawl-pages="):
                    crawl_pages = self._parse_option_int(arg.split("=", 1)[1], 2)
                elif arg.startswith("--crawl="):
                    crawl_pages = self._parse_option_int(arg.split("=", 1)[1], 2)
                elif arg in {"--crawl-pages", "--crawl"} and i + 1 < len(args):
                    i += 1
                    crawl_pages = self._parse_option_int(args[i], 2)
                elif arg.startswith("--skill="):
                    explicit_skill = arg.split("=", 1)[1].strip() or None
                elif arg == "--skill" and i + 1 < len(args):
                    i += 1
                    explicit_skill = args[i].strip() or None
                else:
                    task_parts.append(arg)
                i += 1

            task_text = " ".join(task_parts).strip()
            if not task_text:
                print("用法：do <goal> [--skill=name] [--dry-run] [--strict] [--js] [--top=N] [--crawl-assist] [--crawl-pages=N] [--html-first|--no-html-first]")
                return True

            result = await self.agent.run_do_task(
                task=task_text,
                html_first=html_first,
                top_results=top_results,
                use_browser=use_browser,
                crawl_assist=crawl_assist,
                crawl_pages=crawl_pages,
                strict=strict,
                dry_run=dry_run,
                explicit_skill=explicit_skill,
                command_name="do",
            )
            self._print_result(result)

        elif command in {"do-plan", "do_plan", "plan"}:
            # 阶段化技能剧本：先给 AI 一组稳定的 CLI 步骤，再决定执行。
            task_parts: List[str] = []
            explicit_skill: Optional[str] = None
            use_browser: Optional[bool] = None
            html_first: Optional[bool] = None
            crawl_assist: Optional[bool] = None
            top_results: Optional[int] = None
            crawl_pages: Optional[int] = None
            strict = False

            i = 0
            while i < len(args):
                arg = args[i]
                if arg == "--strict":
                    strict = True
                elif arg == "--js":
                    use_browser = True
                elif arg == "--no-js":
                    use_browser = False
                elif arg == "--crawl-assist":
                    crawl_assist = True
                elif arg == "--no-crawl-assist":
                    crawl_assist = False
                elif arg == "--html-first":
                    html_first = True
                elif arg == "--no-html-first":
                    html_first = False
                elif arg.startswith("--top="):
                    top_results = self._parse_option_int(arg.split("=", 1)[1], 5)
                elif arg == "--top" and i + 1 < len(args):
                    i += 1
                    top_results = self._parse_option_int(args[i], 5)
                elif arg.startswith("--crawl-pages="):
                    crawl_pages = self._parse_option_int(arg.split("=", 1)[1], 2)
                elif arg.startswith("--crawl="):
                    crawl_pages = self._parse_option_int(arg.split("=", 1)[1], 2)
                elif arg in {"--crawl-pages", "--crawl"} and i + 1 < len(args):
                    i += 1
                    crawl_pages = self._parse_option_int(args[i], 2)
                elif arg.startswith("--skill="):
                    explicit_skill = arg.split("=", 1)[1].strip() or None
                elif arg == "--skill" and i + 1 < len(args):
                    i += 1
                    explicit_skill = args[i].strip() or None
                else:
                    task_parts.append(arg)
                i += 1

            task_text = " ".join(task_parts).strip()
            if not task_text:
                print("用法：do-plan <goal> [--skill=name] [--strict] [--js] [--top=N] [--crawl-assist] [--crawl-pages=N] [--html-first|--no-html-first]")
                return True

            payload = self.agent.build_skill_playbook(
                task=task_text,
                explicit_skill=explicit_skill,
                html_first=html_first,
                top_results=top_results,
                use_browser=use_browser,
                crawl_assist=crawl_assist,
                crawl_pages=crawl_pages,
                strict=strict,
                command_name="do-plan",
            )
            self._print_result(payload)

        elif command in {"do-submit", "do_submit"}:
            # 长任务异步提交：创建本地作业并后台执行。
            task_parts: List[str] = []
            explicit_skill: Optional[str] = None
            use_browser: Optional[bool] = None
            html_first: Optional[bool] = None
            crawl_assist: Optional[bool] = None
            top_results: Optional[int] = None
            crawl_pages: Optional[int] = None
            timeout_sec: Optional[int] = None
            strict = False

            i = 0
            while i < len(args):
                arg = args[i]
                if arg == "--strict":
                    strict = True
                elif arg == "--js":
                    use_browser = True
                elif arg == "--no-js":
                    use_browser = False
                elif arg == "--crawl-assist":
                    crawl_assist = True
                elif arg == "--no-crawl-assist":
                    crawl_assist = False
                elif arg == "--html-first":
                    html_first = True
                elif arg == "--no-html-first":
                    html_first = False
                elif arg.startswith("--top="):
                    top_results = self._parse_option_int(arg.split("=", 1)[1], 5)
                elif arg == "--top" and i + 1 < len(args):
                    i += 1
                    top_results = self._parse_option_int(args[i], 5)
                elif arg.startswith("--crawl-pages="):
                    crawl_pages = self._parse_option_int(arg.split("=", 1)[1], 2)
                elif arg.startswith("--crawl="):
                    crawl_pages = self._parse_option_int(arg.split("=", 1)[1], 2)
                elif arg in {"--crawl-pages", "--crawl"} and i + 1 < len(args):
                    i += 1
                    crawl_pages = self._parse_option_int(args[i], 2)
                elif arg.startswith("--timeout-sec="):
                    timeout_sec = self._parse_option_int(arg.split("=", 1)[1], 900)
                elif arg == "--timeout-sec" and i + 1 < len(args):
                    i += 1
                    timeout_sec = self._parse_option_int(args[i], 900)
                elif arg.startswith("--skill="):
                    explicit_skill = arg.split("=", 1)[1].strip() or None
                elif arg == "--skill" and i + 1 < len(args):
                    i += 1
                    explicit_skill = args[i].strip() or None
                else:
                    task_parts.append(arg)
                i += 1

            task_text = " ".join(task_parts).strip()
            if not task_text:
                print("用法：do-submit <goal> [--skill=name] [--strict] [--js] [--top=N] [--crawl-assist] [--crawl-pages=N] [--timeout-sec=N] [--html-first|--no-html-first]")
                return True

            options = {
                "html_first": html_first,
                "top_results": top_results,
                "use_browser": use_browser,
                "crawl_assist": crawl_assist,
                "crawl_pages": crawl_pages,
                "timeout_sec": timeout_sec,
            }
            job = self._job_store.create_do_job(
                task=task_text,
                options=options,
                skill=explicit_skill,
                strict=strict,
                source="cli_do_submit",
            )
            spawned = spawn_job_worker(
                job_id=job["id"],
                python_executable=sys.executable,
                main_script=Path(__file__).resolve(),
            )
            updated = self._job_store.update_job(
                job["id"],
                pid=spawned.get("pid"),
                worker_command=spawned.get("cmd"),
                status="queued",
            )
            self._print_result(
                {
                    "success": True,
                    "job": updated or job,
                    "next": [
                        f"python main.py job-status {job['id']}",
                        f"python main.py job-result {job['id']}",
                    ],
                }
            )

        elif command in {"jobs"}:
            limit = 20
            status_filter: Optional[str] = None
            i = 0
            while i < len(args):
                arg = args[i]
                if arg.startswith("--limit="):
                    limit = self._parse_option_int(arg.split("=", 1)[1], limit)
                elif arg == "--limit" and i + 1 < len(args):
                    i += 1
                    limit = self._parse_option_int(args[i], limit)
                elif arg.startswith("--status="):
                    status_filter = arg.split("=", 1)[1].strip() or None
                elif arg == "--status" and i + 1 < len(args):
                    i += 1
                    status_filter = args[i].strip() or None
                i += 1
            items = self._job_store.list_jobs(limit=limit, status=status_filter)
            self._print_result(
                {
                    "success": True,
                    "count": len(items),
                    "jobs": items,
                }
            )

        elif command in {"job-status", "job_status"} and args:
            job_id = str(args[0]).strip()
            include_result = "--with-result" in args
            meta = self._job_store.get_job(job_id)
            if not meta:
                self._print_result(
                    {
                        "success": False,
                        "error": f"job_not_found:{job_id}",
                    }
                )
                return True
            payload: Dict[str, Any] = {
                "success": True,
                "job": meta,
            }
            if include_result:
                payload["result"] = self._job_store.read_result(job_id)
            self._print_result(payload)

        elif command in {"job-result", "job_result"} and args:
            job_id = str(args[0]).strip()
            result_payload = self._job_store.read_result(job_id)
            meta = self._job_store.get_job(job_id)
            if result_payload is None:
                self._print_result(
                    {
                        "success": False,
                        "error": f"job_result_not_found:{job_id}",
                        "job": meta,
                    }
                )
                return True
            self._print_result(
                {
                    "success": True,
                    "job": meta,
                    "result": result_payload,
                }
            )

        elif command in {"job-worker", "job_worker"} and args:
            job_id = str(args[0]).strip()
            payload = await self._run_job_worker(job_id)
            self._print_result(payload)

        elif command in {"skills", "skill-profiles", "skill_profiles"}:
            resolve_text: Optional[str] = None
            probe_parts: List[str] = []
            compact_mode = False
            full_catalog = False
            i = 0
            while i < len(args):
                arg = args[i]
                if arg.startswith("--resolve="):
                    resolve_text = arg.split("=", 1)[1].strip() or None
                elif arg == "--resolve" and i + 1 < len(args):
                    i += 1
                    resolve_text = args[i].strip() or None
                elif arg in {"--compact", "--brief"}:
                    compact_mode = True
                elif arg == "--full":
                    full_catalog = True
                elif not arg.startswith("--"):
                    probe_parts.append(arg)
                i += 1
            if not resolve_text and probe_parts:
                resolve_text = " ".join(probe_parts).strip() or None

            if resolve_text:
                probe = self.agent.build_skill_probe(
                    task=resolve_text,
                    command_name="skills_probe",
                )
                use_compact = compact_mode or not full_catalog
                payload = {
                    "success": bool(probe.get("success")),
                    "probe": probe,
                }
                if use_compact:
                    payload["mode"] = "compact_probe"
                    payload["hint"] = "Use `skills --resolve \"<goal>\" --full` to include full catalog."
                else:
                    catalog = self.agent.get_skill_profiles()
                    payload.update(catalog)
            else:
                catalog = self.agent.get_skill_profiles()
                payload = {"success": True, **catalog}
            self._print_result(payload)

        elif command in {"ir-lint", "ir_lint", "lint-ir", "lint_ir"} and args:
            raw_input = " ".join(args).strip()
            if not raw_input:
                print("用法：ir-lint <ir-file|json|workflow-file|workflow-json>")
                return True
            try:
                data = self._load_workflow_spec(raw_input)
            except Exception as exc:
                self._print_result({
                    "success": False,
                    "error": f"IR 解析失败: {exc}",
                })
                return True

            if isinstance(data, dict) and "workflow" in data and "goal" in data:
                ir_payload = data
            elif isinstance(data, dict) and "steps" in data:
                ir_payload = build_command_ir(
                    command="ir-lint",
                    goal="lint_workflow_only",
                    route="general",
                    workflow_spec=data,
                    options={},
                    dry_run=True,
                )
            else:
                self._print_result({
                    "success": False,
                    "error": "输入必须是 command IR 或 workflow spec(JSON object)",
                })
                return True

            issues = lint_command_ir(ir_payload, workflow_schema=self.agent.get_workflow_schema())
            summary = summarize_lint(issues)
            self._print_result({
                "success": not has_lint_errors(issues),
                "lint": {
                    **summary,
                    "issues": issues,
                },
                "ir": ir_payload,
            })

        elif command in {"quick", "q"} and args:
            # 默认入口：workflow 编排优先 + HTML-first 分析
            use_browser = "--js" in args
            crawl_pages = 3
            top_results = 5
            html_first = True
            strict = False
            crawl_assist = False
            legacy = False
            input_parts = []
            i = 0
            while i < len(args):
                arg = args[i]
                if arg == "--js":
                    pass
                elif arg == "--legacy":
                    legacy = True
                elif arg == "--strict":
                    strict = True
                elif arg == "--crawl-assist":
                    crawl_assist = True
                elif arg == "--no-html-first":
                    html_first = False
                elif arg == "--html-first":
                    html_first = True
                elif arg.startswith("--top="):
                    top_results = self._parse_option_int(arg.split("=", 1)[1], top_results)
                elif arg == "--top" and i + 1 < len(args):
                    i += 1
                    top_results = self._parse_option_int(args[i], top_results)
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
                print("用法：quick <url|query> [--js] [--top=N] [--html-first|--no-html-first] [--crawl-assist] [--crawl-pages=N] [--strict] [--legacy]")
                return True

            await self._run_inferred_input(
                raw_input,
                use_browser=use_browser,
                crawl_pages=crawl_pages,
                top_results=top_results,
                html_first=html_first,
                strict=strict,
                crawl_assist=crawl_assist,
                legacy=legacy,
            )

        elif command in {"task", "orchestrate", "auto"} and args:
            use_browser = "--js" in args
            crawl_pages = 2
            top_results = 5
            html_first = True
            strict = False
            crawl_assist = False
            input_parts = []
            i = 0
            while i < len(args):
                arg = args[i]
                if arg == "--js":
                    pass
                elif arg == "--strict":
                    strict = True
                elif arg == "--crawl-assist":
                    crawl_assist = True
                elif arg == "--no-html-first":
                    html_first = False
                elif arg == "--html-first":
                    html_first = True
                elif arg.startswith("--top="):
                    top_results = self._parse_option_int(arg.split("=", 1)[1], top_results)
                elif arg == "--top" and i + 1 < len(args):
                    i += 1
                    top_results = self._parse_option_int(args[i], top_results)
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

            task_input = " ".join(input_parts).strip()
            if not task_input:
                print("用法：task <goal> [--js] [--top=N] [--html-first|--no-html-first] [--crawl-assist] [--crawl-pages=N] [--strict]")
                return True

            result = await self.agent.orchestrate_task(
                task=task_input,
                html_first=html_first,
                top_results=top_results,
                use_browser=use_browser,
                crawl_assist=crawl_assist,
                crawl_pages=crawl_pages,
                strict=strict,
            )
            self._print_result(result)

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
            num_results = 10
            engine_tokens: List[str] = []
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
                elif arg.startswith("--num-results="):
                    num_results = self._parse_option_int(arg.split("=", 1)[1], num_results)
                elif arg == "--num-results" and i + 1 < len(args):
                    i += 1
                    num_results = self._parse_option_int(args[i], num_results)
                elif arg.startswith("--engine="):
                    raw = arg.split("=", 1)[1]
                    engine_tokens.extend([x.strip() for x in raw.split(",") if x.strip()])
                elif arg.startswith("--engines="):
                    raw = arg.split("=", 1)[1]
                    engine_tokens.extend([x.strip() for x in raw.split(",") if x.strip()])
                elif arg in {"--engine", "--engines"} and i + 1 < len(args):
                    i += 1
                    engine_tokens.extend([x.strip() for x in args[i].split(",") if x.strip()])
                else:
                    query_parts.append(arg)
                i += 1

            query = " ".join(query_parts).strip()
            if not query:
                print("用法：web <query> [--no-crawl] [--crawl-pages=N] [--num-results=N] [--engine=name|a,b]")
                return True

            if engine_tokens:
                engines, unknown = self._resolve_advanced_engines(engine_tokens)
                if unknown:
                    self._print_result(
                        {
                            "success": False,
                            "error": "unknown_engine_tokens",
                            "unknown": unknown,
                            "supported": self._supported_advanced_engine_tokens(),
                        }
                    )
                    return True
                deep_search = DeepSearchEngine()
                try:
                    result = await deep_search.deep_search(
                        query,
                        num_results=max(1, num_results),
                        use_english=not bool(re.search(r"[\u4e00-\u9fff]", query)),
                        engines=engines or None,
                        crawl_top=(max(0, crawl_pages) if auto_crawl else 0),
                        query_variants=1,
                    )
                finally:
                    await deep_search.close()
                self._print_result(result)
            else:
                result = await self.agent.search_internet(
                    query,
                    num_results=max(1, num_results),
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

        elif command in {"auth-profiles", "auth_profiles", "login-profiles", "login_profiles"}:
            data = self.agent.get_auth_profiles()
            self._print_result({"success": True, **data})

        elif command in {"auth-hint", "auth_hint", "login-hint", "login_hint"}:
            if not args:
                print("用法：auth-hint <url>")
                return True
            data = self.agent.get_auth_hint(args[0])
            self._print_result({"success": True, **data})

        elif command in {"auth-template", "auth_template", "login-template", "login_template"}:
            output_path: Optional[str] = None
            force = False
            i = 0
            while i < len(args):
                arg = args[i]
                if arg == "--force":
                    force = True
                elif arg.startswith("--output="):
                    output_path = arg.split("=", 1)[1].strip() or output_path
                elif arg == "--output" and i + 1 < len(args):
                    i += 1
                    output_path = args[i].strip() or output_path
                elif not arg.startswith("--") and output_path is None:
                    output_path = arg.strip()
                i += 1

            try:
                data = self.agent.export_auth_template(output_path=output_path, force=force)
                self._print_result(data)
            except FileExistsError as exc:
                self._print_result({
                    "success": False,
                    "error": str(exc),
                    "hint": "目标文件已存在。追加 --force 覆盖，或指定新的输出路径。",
                })
            except Exception as exc:
                self._print_result({
                    "success": False,
                    "error": str(exc),
                })

        elif command in {"workflow-schema", "workflow_schema", "flow-schema", "flow_schema"}:
            data = self.agent.get_workflow_schema()
            self._print_result({"success": True, **data})

        elif command in {"workflow-template", "workflow_template", "flow-template", "flow_template"}:
            output_path: Optional[str] = None
            scenario = "social_comments"
            force = False
            i = 0
            while i < len(args):
                arg = args[i]
                if arg == "--force":
                    force = True
                elif arg.startswith("--scenario="):
                    scenario = arg.split("=", 1)[1].strip() or scenario
                elif arg == "--scenario" and i + 1 < len(args):
                    i += 1
                    scenario = args[i].strip() or scenario
                elif arg.startswith("--output="):
                    output_path = arg.split("=", 1)[1].strip() or output_path
                elif arg == "--output" and i + 1 < len(args):
                    i += 1
                    output_path = args[i].strip() or output_path
                elif not arg.startswith("--") and output_path is None:
                    output_path = arg.strip()
                i += 1

            try:
                data = self.agent.export_workflow_template(
                    output_path=output_path,
                    scenario=scenario,
                    force=force,
                )
                self._print_result(data)
            except FileExistsError as exc:
                self._print_result({
                    "success": False,
                    "error": str(exc),
                    "hint": "目标文件已存在。追加 --force 覆盖，或指定新的输出路径。",
                })
            except Exception as exc:
                self._print_result({
                    "success": False,
                    "error": str(exc),
                })

        elif command in {"workflow", "flow"}:
            strict = False
            dry_run = False
            spec_parts: List[str] = []
            overrides: Dict[str, Any] = {}
            i = 0
            while i < len(args):
                arg = args[i]
                if arg == "--strict":
                    strict = True
                elif arg == "--dry-run":
                    dry_run = True
                elif arg.startswith("--var=") or arg.startswith("--set="):
                    raw_pair = arg.split("=", 1)[1]
                    key, value = self._parse_key_value_pair(raw_pair)
                    if key:
                        self._set_nested_value(overrides, key, value)
                elif arg in {"--var", "--set"} and i + 1 < len(args):
                    i += 1
                    key, value = self._parse_key_value_pair(args[i])
                    if key:
                        self._set_nested_value(overrides, key, value)
                else:
                    spec_parts.append(arg)
                i += 1

            spec_input = " ".join(spec_parts).strip()
            if not spec_input:
                print("用法：workflow <spec-file|json> [--var key=value] [--set key=value] [--strict] [--dry-run]")
                print("示例：workflow .web-rooter/workflow.social.json --var topic='AI Agent 评论' --var top_hits=8")
                print("先生成模板：workflow-template .web-rooter/workflow.social.json --scenario=social_comments --force")
                return True

            try:
                spec = self._load_workflow_spec(spec_input)
            except Exception as exc:
                self._print_result({
                    "success": False,
                    "error": f"workflow spec 解析失败: {exc}",
                    "hint": "确认是有效 JSON，或传入存在的 JSON 文件路径。",
                })
                return True

            workflow_ir = build_command_ir(
                command="workflow",
                goal=f"workflow:{spec.get('name', 'adhoc')}",
                route="auto",
                workflow_spec=spec,
                options={"variable_overrides": bool(overrides)},
                strict=strict,
                dry_run=dry_run,
            )
            workflow_issues = lint_command_ir(workflow_ir, workflow_schema=self.agent.get_workflow_schema())
            workflow_lint = {
                **summarize_lint(workflow_issues),
                "issues": workflow_issues,
            }
            if has_lint_errors(workflow_issues):
                self._print_result({
                    "success": False,
                    "error": "workflow_ir_lint_failed",
                    "lint": workflow_lint,
                    "ir": workflow_ir,
                })
                return True

            if dry_run:
                self._print_result({
                    "success": True,
                    "message": "workflow dry-run only, not executed",
                    "lint": workflow_lint,
                    "ir": workflow_ir,
                })
                return True

            result = await self.agent.run_workflow_spec(
                spec=spec,
                variable_overrides=overrides or None,
                strict=strict,
            )
            if isinstance(result.data, dict):
                result.data["ir"] = workflow_ir
                result.data["lint"] = workflow_lint
            self._print_result(result)

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
            engine_tokens: List[str] = []
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
                elif arg.startswith("--engine="):
                    raw = arg.split("=", 1)[1]
                    engine_tokens.extend([x.strip() for x in raw.split(",") if x.strip()])
                elif arg.startswith("--engines="):
                    raw = arg.split("=", 1)[1]
                    engine_tokens.extend([x.strip() for x in raw.split(",") if x.strip()])
                elif arg in {"--engine", "--engines"} and i + 1 < len(args):
                    i += 1
                    engine_tokens.extend([x.strip() for x in args[i].split(",") if x.strip()])
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
                print("用法：deep <query> [--en] [--crawl=N] [--num-results=N] [--variants=N] [--engine=name|a,b] [--news] [--platforms] [--commerce] [--channel=x,y]")
                return True

            selected_engines: Optional[List[AdvancedSearchEngine]] = None
            if engine_tokens:
                resolved_engines, unknown = self._resolve_advanced_engines(engine_tokens)
                if unknown:
                    self._print_result(
                        {
                            "success": False,
                            "error": "unknown_engine_tokens",
                            "unknown": unknown,
                            "supported": self._supported_advanced_engine_tokens(),
                        }
                    )
                    return True
                selected_engines = resolved_engines or None

            logger.info(
                "执行深度搜索：%s, 英文搜索：%s, 爬取前%s个结果, 渠道=%s, engines=%s",
                query,
                use_en,
                crawl,
                ",".join(channel_profiles) if channel_profiles else "default",
                ",".join([e.value for e in selected_engines]) if selected_engines else "default",
            )
            deep_search = DeepSearchEngine()
            try:
                result = await deep_search.deep_search(
                    query,
                    num_results=num_results,
                    use_english=use_en,
                    engines=selected_engines,
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
                unknown_payload = self._build_unknown_command_payload(command, args=args)
                if unknown_payload:
                    self._print_result(unknown_payload)
                    return True

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
        top_results: int = 5,
        html_first: bool = True,
        strict: bool = False,
        crawl_assist: bool = False,
        legacy: bool = False,
    ):
        """根据输入自动判定执行方式（默认：workflow 编排 + HTML-first）。"""
        if legacy:
            if self._looks_like_url(raw_input):
                result = await self.agent.visit(raw_input, use_browser=use_browser)
            else:
                result = await self.agent.search_internet(
                    raw_input,
                    auto_crawl=True,
                    crawl_pages=max(0, crawl_pages),
                )
            self._print_result(result)
            return

        result = await self.agent.orchestrate_task(
            task=raw_input,
            html_first=html_first,
            top_results=max(1, top_results),
            use_browser=use_browser,
            crawl_assist=crawl_assist,
            crawl_pages=max(1, crawl_pages),
            strict=strict,
        )
        self._print_result(result)

    def _evaluate_safe_mode_guard(self, command: str, args: List[str]) -> Dict[str, Any]:
        state = self._safe_mode.get_state()
        decision = evaluate_safe_mode_command(command=command, args=args, state=state)
        decision["state"] = self._safe_mode.describe()
        decision["command"] = command
        return decision

    def _handle_safe_mode_command(self, args: List[str]) -> Dict[str, Any]:
        action = "status"
        policy: Optional[str] = None
        i = 0
        while i < len(args):
            arg = str(args[i]).strip().lower()
            if arg in {"on", "off", "status"}:
                action = arg
            elif arg.startswith("--policy="):
                policy = arg.split("=", 1)[1].strip() or None
            elif arg == "--policy" and i + 1 < len(args):
                i += 1
                policy = str(args[i]).strip().lower() or None
            i += 1

        if action == "status":
            return {"success": True, "safe_mode": self._safe_mode.describe()}
        if action == "on":
            return {
                "success": True,
                "safe_mode": self._safe_mode.set_enabled(True, policy=policy),
                "message": "safe mode enabled",
            }
        if action == "off":
            return {
                "success": True,
                "safe_mode": self._safe_mode.set_enabled(False, policy=policy),
                "message": "safe mode disabled",
            }
        return {
            "success": False,
            "error": f"unknown_safe_mode_action:{action}",
        }

    async def _run_job_worker(self, job_id: str) -> Dict[str, Any]:
        record = self._job_store.get_job(job_id)
        if not record:
            return {
                "success": False,
                "error": f"job_not_found:{job_id}",
            }

        status = str(record.get("status") or "").strip().lower()
        if status in {"completed", "failed", "cancelled"}:
            return {
                "success": status == "completed",
                "job": record,
                "result": self._job_store.read_result(job_id),
            }

        self._job_store.update_job(
            job_id,
            status="running",
            pid=os.getpid(),
            started_at=record.get("started_at") or datetime.utcnow().isoformat() + "Z",
            error=None,
        )
        current = self._job_store.get_job(job_id) or record
        options = current.get("options") if isinstance(current.get("options"), dict) else {}
        task_text = str(current.get("task") or "").strip()
        skill = str(current.get("skill") or "").strip() or None
        strict = bool(current.get("strict", False))
        timeout_sec = max(30, self._parse_option_int(str(options.get("timeout_sec") or 0), 900))

        try:
            response = await asyncio.wait_for(
                self.agent.run_do_task(
                    task=task_text,
                    explicit_skill=skill,
                    strict=strict,
                    dry_run=False,
                    command_name="job-worker",
                    html_first=options.get("html_first"),
                    top_results=options.get("top_results"),
                    use_browser=options.get("use_browser"),
                    crawl_assist=options.get("crawl_assist"),
                    crawl_pages=options.get("crawl_pages"),
                ),
                timeout=float(timeout_sec),
            )
            payload = response.to_dict() if hasattr(response, "to_dict") else response
            result_path = self._job_store.write_result(job_id, payload if isinstance(payload, dict) else {"result": payload})
            next_status = "completed" if bool(response.success) else "failed"
            updated = self._job_store.update_job(
                job_id,
                status=next_status,
                finished_at=datetime.utcnow().isoformat() + "Z",
                error=(None if response.success else response.error),
                result_path=result_path,
            )
            return {
                "success": bool(response.success),
                "job": updated,
                "result": payload,
            }
        except asyncio.TimeoutError:
            updated = self._job_store.update_job(
                job_id,
                status="failed",
                finished_at=datetime.utcnow().isoformat() + "Z",
                error=f"job_timeout:{timeout_sec}s",
            )
            return {
                "success": False,
                "job": updated,
                "error": f"job_timeout:{timeout_sec}s",
            }
        except Exception as exc:
            updated = self._job_store.update_job(
                job_id,
                status="failed",
                finished_at=datetime.utcnow().isoformat() + "Z",
                error=str(exc),
            )
            return {
                "success": False,
                "job": updated,
                "error": str(exc),
            }

    @staticmethod
    def _looks_like_url(text: str) -> bool:
        value = text.strip().lower()
        return value.startswith(("http://", "https://", "www."))

    @classmethod
    def _command_suggestions(cls, command: str, limit: int = 3) -> List[str]:
        token = str(command or "").strip().lower()
        if not token:
            return []
        return difflib.get_close_matches(
            token,
            sorted(cls._KNOWN_COMMAND_ALIASES),
            n=max(1, int(limit)),
            cutoff=0.74,
        )

    @staticmethod
    def _looks_like_command_typo(command: str) -> bool:
        token = str(command or "").strip().lower()
        if not token:
            return False
        return bool(re.match(r"^[a-z][a-z0-9_-]{1,31}$", token))

    def _build_unknown_command_payload(self, command: str, args: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        suggestions = self._command_suggestions(command)
        if not suggestions or not self._looks_like_command_typo(command):
            return None
        payload: Dict[str, Any] = {
            "success": False,
            "error": f"unknown_command:{command}",
            "hint": "Possible command typo. Use suggested commands, or use `quick`/`do` for free-form goals.",
            "suggestions": suggestions,
            "recommended": [
                f"python main.py {suggestions[0]} ...",
                "python main.py do-plan \"<goal>\"",
                "python main.py do \"<goal>\"",
            ],
        }

        arg_tokens: List[str] = []
        if args:
            arg_tokens = [
                str(item).strip()
                for item in args
                if str(item).strip() and not str(item).strip().startswith("--")
            ]
        goal_text = " ".join(arg_tokens).strip() if arg_tokens else str(command or "").strip()

        if self.agent and goal_text:
            try:
                probe = self.agent.build_skill_probe(
                    task=goal_text,
                    command_name="unknown_command_recover",
                )
            except Exception:
                probe = {}
            if isinstance(probe, dict) and probe.get("success"):
                selected_skill = str(probe.get("selected_skill") or "").strip()
                route = str(probe.get("route") or "").strip()
                escaped_goal = goal_text.replace('"', '\\"')
                if selected_skill:
                    payload["recommended"] = [
                        f'python main.py do-plan "{escaped_goal}" --skill={selected_skill}',
                        f'python main.py do "{escaped_goal}" --skill={selected_skill} --dry-run',
                        f'python main.py do "{escaped_goal}" --skill={selected_skill}',
                    ]
                payload["auto_resolution"] = {
                    "goal": goal_text,
                    "selected_skill": (selected_skill or None),
                    "route": (route or None),
                    "confidence": probe.get("confidence"),
                }
        return payload

    @classmethod
    def _advanced_engine_alias_map(cls) -> Dict[str, AdvancedSearchEngine]:
        mapping: Dict[str, AdvancedSearchEngine] = {
            engine.value: engine for engine in AdvancedSearchEngine
        }
        mapping.update(
            {
                "ddg": AdvancedSearchEngine.DUCKDUCKGO,
                "duck": AdvancedSearchEngine.DUCKDUCKGO,
                "quarkcn": AdvancedSearchEngine.QUARK,
                "quark_sm": AdvancedSearchEngine.QUARK,
                "xhs": AdvancedSearchEngine.XIAOHONGSHU,
                "bili": AdvancedSearchEngine.BILIBILI,
                "x": AdvancedSearchEngine.TWITTER,
                "jdcom": AdvancedSearchEngine.JD,
                "jingdong": AdvancedSearchEngine.JD,
                "pdd": AdvancedSearchEngine.PINDUODUO,
                "scholar": AdvancedSearchEngine.GOOGLE_SCHOLAR,
                "semantic": AdvancedSearchEngine.SEMANTIC_SCHOLAR,
            }
        )
        return mapping

    @classmethod
    def _supported_advanced_engine_tokens(cls) -> List[str]:
        preferred = [
            "google", "bing", "quark", "baidu", "duckduckgo", "sogou", "yandex",
            "google_us", "bing_us",
            "xiaohongshu", "zhihu", "tieba", "douyin", "weibo", "bilibili", "reddit", "twitter", "hackernews",
            "taobao", "jd", "pinduoduo", "meituan",
            "github", "stackoverflow", "medium",
            "google_scholar", "arxiv", "semantic_scholar",
        ]
        alias_map = cls._advanced_engine_alias_map()
        extras = sorted([token for token in alias_map.keys() if token not in preferred])
        return preferred + extras

    def _resolve_advanced_engines(self, tokens: List[str]) -> tuple[List[AdvancedSearchEngine], List[str]]:
        alias_map = self._advanced_engine_alias_map()
        resolved: List[AdvancedSearchEngine] = []
        seen = set()
        unknown: List[str] = []

        for raw in tokens:
            normalized = str(raw or "").strip().lower().replace("-", "_")
            if not normalized:
                continue
            engine = alias_map.get(normalized)
            if engine is None:
                unknown.append(raw)
                continue
            if engine.value in seen:
                continue
            seen.add(engine.value)
            resolved.append(engine)

        return resolved, unknown

    @staticmethod
    def _parse_option_int(value: str, default: int) -> int:
        """安全解析整数参数。"""
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _parse_scalar_or_json(value: str) -> Any:
        raw = (value or "").strip()
        if raw == "":
            return ""
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    @classmethod
    def _parse_key_value_pair(cls, raw: str) -> tuple[Optional[str], Any]:
        text = (raw or "").strip()
        if "=" not in text:
            return None, None
        key, value = text.split("=", 1)
        normalized_key = key.strip()
        if not normalized_key:
            return None, None
        return normalized_key, cls._parse_scalar_or_json(value)

    @staticmethod
    def _set_nested_value(target: Dict[str, Any], dotted_key: str, value: Any) -> None:
        parts = [item.strip() for item in str(dotted_key or "").split(".") if item.strip()]
        if not parts:
            return
        current = target
        for part in parts[:-1]:
            next_value = current.get(part)
            if not isinstance(next_value, dict):
                next_value = {}
                current[part] = next_value
            current = next_value
        current[parts[-1]] = value

    @staticmethod
    def _load_workflow_spec(spec_input: str) -> Dict[str, Any]:
        candidate = Path(spec_input).expanduser()
        if candidate.exists():
            with candidate.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("workflow file root must be a JSON object")
            return data

        data = json.loads(spec_input)
        if not isinstance(data, dict):
            raise ValueError("workflow JSON root must be an object")
        return data

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
  html <url> [--js] [--max-chars=N] [--no-fallback]
                                  - 获取原始 HTML（推荐 AI 做结构分析）
  do <goal> [--skill=name] [--dry-run] [--strict] [--js] [--top=N] [--crawl-assist] [--crawl-pages=N] [--html-first|--no-html-first]
                                  - 单入口：Intent -> Skill -> IR -> Lint -> Execute
  do-plan <goal> [--skill=name] [--strict] [--js] [--top=N] [--crawl-assist] [--crawl-pages=N] [--html-first|--no-html-first]
                                  - 先输出阶段化 skills 剧本与推荐 CLI 序列
  do-submit <goal> [--skill=name] [--strict] [--js] [--top=N] [--crawl-assist] [--crawl-pages=N] [--timeout-sec=N] [--html-first|--no-html-first]
                                  - 提交长任务到后台作业系统（非阻塞）
  quick <url|query> [--js] [--top=N] [--html-first|--no-html-first] [--crawl-assist] [--crawl-pages=N] [--strict] [--legacy]
                                  - 默认智能入口（workflow 编排优先；--legacy 回退旧逻辑）
  task <goal> [--js] [--top=N] [--html-first|--no-html-first] [--crawl-assist] [--crawl-pages=N] [--strict]
                                  - AI 默认任务入口（推荐）
  search <query> [url]            - 在已访问页面中搜索
  extract <url> <target>          - 提取特定信息
  crawl <url> [pages] [depth] [--pattern=REGEX] [--allow-external] [--no-subdomains]
  links <url> [--all]             - 获取链接
  kb / knowledge                  - 查看知识库
  fetch <url>                     - 获取页面

【互联网搜索】
  web <query> [--no-crawl] [--crawl-pages=N] [--num-results=N] [--engine=name|a,b]
  deep <query> [--en] [--crawl=N] [--num-results=N] [--variants=N] [--engine=name|a,b] [--news] [--platforms] [--commerce] [--channel=x,y]
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
  workflow-schema                 - 查看 AI 可编排 workflow schema
  workflow-template [path] [--scenario=social_comments|academic_relations] [--force]
                                  - 导出 workflow 模板（本地改造后可直接运行）
  workflow <spec-file|json> [--var key=value] [--set key=value] [--strict] [--dry-run]
                                  - 运行声明式工作流（AI 可自主决策每一步）
  skills [--resolve "<goal>"] [--compact|--full]
                                  - skills 探针（默认紧凑模式，可切换完整目录）
  ir-lint <ir-file|json|workflow-file|workflow-json>
                                  - 对 command IR / workflow 进行 lint（执行前校验）
  jobs [--limit=N] [--status=queued|running|completed|failed]
                                  - 查看后台作业列表
  job-status <job_id> [--with-result]
                                  - 查看作业状态（可附带结果）
  job-result <job_id>             - 读取作业结果
  safe-mode [status|on|off] [--policy=strict]
                                  - AI 命令防火墙（strict 模式只允许高层命令）
  doctor                          - 环境自检（依赖/浏览器/抓取链路）
  context [--limit=N] [--event=type] - 查看全局深度抓取上下文事件
  processors [--load=module:obj] [--force] - 查看/加载抓取后处理扩展
  planners [--load=module:obj] [--force] - 查看/加载 MindSearch planner 扩展
  challenge-profiles              - 查看 challenge workflow 路由档案
  auth-profiles                   - 查看本地登录态 profile
  auth-hint <url>                 - 查看指定站点登录态匹配与提示
  auth-template [path] [--force]  - 导出本地登录模板 JSON

【其他】
  help                            - 帮助信息
  quit / exit                     - 退出

示例:
  visit https://example.com
  html https://example.com --max-chars=100000
  do "抓取小红书和知乎关于 iPhone 17 的评论观点并给出处" --dry-run
  do "分析 RAG benchmark 论文关系并给引用" --skill=academic_relation_mining --strict
  do-plan "抓取知乎评论区观点并给出处" --skill=social_comment_mining
  do-submit "分析 RAG benchmark 论文关系并给引用" --skill=academic_relation_mining --strict --timeout-sec=1200
  skills --resolve "抓取知乎评论区观点并给出处" --compact
  skills --resolve "抓取知乎评论区观点并给出处" --full
  jobs --status=running
  job-status <job_id>
  job-result <job_id>
  safe-mode on --policy=strict
  quick https://example.com --js
  quick "WorldQuant alpha101 因子"
  quick "RAG benchmark 2026" --top=6 --html-first
  task "帮我分析这个主题的主流观点并给出处：AI Agent 工程实践" --top=8 --crawl-assist
  web AI 大模型 --no-crawl
  web "RAG benchmark" --engine=quark --num-results=6 --no-crawl
  web AI 大模型 --crawl-pages=5
  deep "苹果发布会" --en --crawl=5 --num-results=20 --variants=3 --news
  deep "RAG benchmark" --engine=quark --num-results=8 --crawl=0
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
  auth-template
  auth-template .web-rooter/login_profiles.json --force
  auth-hint https://www.zhihu.com
  workflow-schema
  workflow-template .web-rooter/workflow.social.json --scenario=social_comments --force
  workflow .web-rooter/workflow.social.json --var topic=\"手机 评测\" --var top_hits=8
  workflow-template .web-rooter/workflow.academic.json --scenario=academic_relations --force
  workflow .web-rooter/workflow.academic.json --var topic=\"RAG evaluation benchmark\" --strict
  doctor
  # 也可直接输入 URL 或查询词（可疑命令拼写会先拦截并给建议）
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
        from core.browser_bootstrap import ensure_browser_ready
        if not ensure_browser_ready():
            print("[MCP] 警告: Chromium 未就绪，JS 渲染功能可能不可用", flush=True)
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

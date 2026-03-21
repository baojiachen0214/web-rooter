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
from copy import deepcopy
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
from core.version import APP_VERSION
from core.terminal_logo import render_logo_from_png
from core.cli_entry import build_cli_command
from core.http_ssl import is_insecure_ssl_enabled
from core.updater import (
    compare_semver_tags,
    fetch_github_releases,
    infer_github_repo_from_git,
    is_git_repo,
    select_latest_release,
    update_git_to_tag,
)

try:
    from rich.console import Console
    from rich.logging import RichHandler
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.table import Table
    from rich.text import Text

    _RICH_AVAILABLE = True
except Exception:
    Console = None  # type: ignore
    RichHandler = None  # type: ignore
    Panel = None  # type: ignore
    Syntax = None  # type: ignore
    Table = None  # type: ignore
    Text = None  # type: ignore
    _RICH_AVAILABLE = False

_LOG_LEVEL_NAME = str(os.getenv("WEB_ROOTER_LOG_LEVEL", "ERROR")).strip().upper() or "ERROR"
_LOG_LEVEL = getattr(logging, _LOG_LEVEL_NAME, logging.WARNING)
_LOG_NO_RICH = str(os.getenv("WEB_ROOTER_NO_RICH_LOG", "0")).strip().lower() in {"1", "true", "yes", "on"}
_LOG_FORCE_RICH = str(os.getenv("WEB_ROOTER_FORCE_RICH_LOG", "0")).strip().lower() in {"1", "true", "yes", "on"}
_LOG_IS_TTY = bool(getattr(sys.stderr, "isatty", lambda: False)())
_USE_RICH_LOG = _RICH_AVAILABLE and (not _LOG_NO_RICH) and (_LOG_FORCE_RICH or _LOG_IS_TTY)

if _USE_RICH_LOG:
    rich_handler_kwargs: Dict[str, Any] = {
        "show_time": True,
        "show_path": False,
        "markup": True,
    }
    if Console is not None:
        rich_handler_kwargs["console"] = Console(stderr=True)
    logging.basicConfig(
        level=_LOG_LEVEL,
        format="%(message)s",
        handlers=[RichHandler(**rich_handler_kwargs)],
        force=True,
    )
else:
    logging.basicConfig(
        level=_LOG_LEVEL,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
        force=True,
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
        "jobs-clean",
        "jobs_clean",
        "job-clean",
        "job_clean",
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
        "artifact",
        "artifacts",
        "graph",
        "events",
        "runtime-events",
        "runtime_events",
        "pressure",
        "runtime-pressure",
        "runtime_pressure",
        "telemetry",
        "budget",
        "budget-telemetry",
        "budget_telemetry",
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
        "update",
        "upgrade",
        "self-update",
        "self_update",
        "help",
        "quit",
        "exit",
        "safe-mode",
        "safe_mode",
        "guard",
    }
    _DEFAULT_COMMAND_TIMEOUT_SEC = 240
    _COMMAND_TIMEOUT_TARGETS = {
        "visit",
        "html",
        "dom",
        "do",
        "quick",
        "q",
        "task",
        "orchestrate",
        "auto",
        "search",
        "extract",
        "crawl",
        "fetch",
        "web",
        "deep",
        "research",
        "mindsearch",
        "ms",
        "social",
        "shopping",
        "shop",
        "commerce",
        "tech",
        "academic",
        "site",
        "workflow",
        "flow",
    }
    _COMMAND_TIMEOUT_RESERVED = {
        "do-submit",
        "do_submit",
        "job-worker",
        "job_worker",
    }

    def __init__(self):
        # Keep a lightweight agent shell available for local/compile-time commands.
        # The crawler/browser runtime is initialized lazily only when a command needs it.
        self.agent: Optional[WebAgent] = WebAgent()
        self.tools: Optional[WebTools] = None
        self._safe_mode = get_safe_mode_manager()
        self._job_store = get_job_store()
        rich_disabled = str(os.getenv("WEB_ROOTER_NO_RICH", "0")).strip().lower() in {"1", "true", "yes", "on"}
        force_rich = str(os.getenv("WEB_ROOTER_FORCE_RICH", "0")).strip().lower() in {"1", "true", "yes", "on"}
        is_tty = bool(getattr(sys.stdout, "isatty", lambda: False)())
        use_rich = _RICH_AVAILABLE and not rich_disabled and (force_rich or is_tty)
        self._console = Console() if use_rich else None
        self._theme = {
            "info": "bold cyan",
            "success": "bold green",
            "warn": "bold yellow",
            "error": "bold red",
            "usage": "magenta",
            "dim": "dim",
        }

    def _print_line(self, text: str, level: str = "info") -> None:
        if self._console:
            style = self._theme.get(level, "")
            if style:
                self._console.print(text, style=style)
            else:
                self._console.print(text)
        else:
            print(text)

    def _print_usage(self, text: str) -> None:
        self._print_line(text, level="usage")

    async def start(self, show_banner: bool = True):
        """启动"""
        if not show_banner:
            return
        if self._console:
            no_color_env = str(os.getenv("NO_COLOR", "")).strip() != ""
            color_logo = bool(getattr(self._console, "color_system", None)) and not no_color_env
            logo = render_logo_from_png(
                Path(__file__).resolve().parent / "LOGO.png",
                width=52,
                max_height=18,
                color=color_logo,
                style="blocks",
            )
            if logo and Text is not None:
                self._console.print(Text.from_ansi(logo))
            if Panel is not None:
                self._console.print(
                    Panel.fit(
                        f"Web-Rooter v{APP_VERSION} 已启动\n输入 'help' 查看可用命令",
                        border_style="cyan",
                    )
                )
            else:
                self._console.print(f"[Web]  Web-Rooter v{APP_VERSION} 已启动")
                self._console.print("输入 'help' 查看可用命令")
        else:
            print(f"[Web]  Web-Rooter v{APP_VERSION} 已启动")
            print("输入 'help' 查看可用命令")
            print()

    async def _ensure_agent_runtime(self) -> None:
        """只在真正需要抓取/浏览器运行时时才初始化重资源依赖。"""
        if self.agent is None:
            self.agent = WebAgent()
        await self.agent._init()

    async def _ensure_tools(self):
        """按需初始化工具集，减少 CLI 冷启动开销。"""
        if self.tools is None:
            self.tools = WebTools()
            await self.tools.initialize()

    async def run_command_safely(self, command: str, args: list[str]) -> bool:
        sanitized_args, command_timeout_sec = self._extract_command_timeout(command, args)
        try:
            if command_timeout_sec and command_timeout_sec > 0:
                return await asyncio.wait_for(
                    self.run_command(command, sanitized_args),
                    timeout=float(command_timeout_sec),
                )
            return await self.run_command(command, sanitized_args)
        except asyncio.TimeoutError:
            self._print_result(self._build_command_timeout_payload(command, command_timeout_sec))
            return True
        except Exception as exc:
            self._print_result(self._build_command_exception_payload(command, exc))
            return True

    @classmethod
    def _is_timeout_managed_command(cls, command: str) -> bool:
        normalized = str(command or "").strip().lower()
        return normalized in cls._COMMAND_TIMEOUT_TARGETS

    @classmethod
    def _extract_command_timeout(cls, command: str, args: List[str]) -> tuple[List[str], Optional[int]]:
        normalized = str(command or "").strip().lower()
        manage_timeout = cls._is_timeout_managed_command(normalized)
        reserve_timeout_flag = normalized in cls._COMMAND_TIMEOUT_RESERVED

        explicit_timeout: Optional[int] = None
        sanitized: List[str] = []
        i = 0

        while i < len(args):
            arg = str(args[i])
            consumed = False

            if arg.startswith("--command-timeout-sec="):
                raw = arg.split("=", 1)[1].strip()
                parsed = cls._parse_option_int(raw, -1)
                if parsed >= 0:
                    explicit_timeout = parsed
                consumed = True
            elif arg == "--command-timeout-sec":
                consumed = True
                if i + 1 < len(args):
                    i += 1
                    parsed = cls._parse_option_int(str(args[i]).strip(), -1)
                    if parsed >= 0:
                        explicit_timeout = parsed
            elif (not reserve_timeout_flag) and arg.startswith("--timeout-sec="):
                raw = arg.split("=", 1)[1].strip()
                parsed = cls._parse_option_int(raw, -1)
                if parsed >= 0:
                    explicit_timeout = parsed
                consumed = True
            elif (not reserve_timeout_flag) and arg == "--timeout-sec":
                consumed = True
                if i + 1 < len(args):
                    i += 1
                    parsed = cls._parse_option_int(str(args[i]).strip(), -1)
                    if parsed >= 0:
                        explicit_timeout = parsed

            if not consumed:
                sanitized.append(arg)
            i += 1

        if explicit_timeout is not None:
            return sanitized, max(0, int(explicit_timeout))

        if not manage_timeout:
            return sanitized, None

        env_default = cls._parse_option_int(
            str(os.getenv("WEB_ROOTER_COMMAND_TIMEOUT_SEC", cls._DEFAULT_COMMAND_TIMEOUT_SEC)),
            cls._DEFAULT_COMMAND_TIMEOUT_SEC,
        )
        timeout_sec = max(0, int(env_default))
        return sanitized, (timeout_sec if timeout_sec > 0 else None)

    def _build_command_timeout_payload(self, command: str, timeout_sec: Optional[int]) -> Dict[str, Any]:
        normalized = str(command or "").strip().lower() or command
        timeout_value = max(1, int(timeout_sec or self._DEFAULT_COMMAND_TIMEOUT_SEC))
        hint = (
            f"命令执行超过 {timeout_value}s 已自动停止。"
            "可增大 `--command-timeout-sec`，或设置 `WEB_ROOTER_COMMAND_TIMEOUT_SEC`。"
        )
        if str(normalized) in {"do", "quick", "q", "task", "orchestrate", "auto"}:
            hint += " 对超长任务建议改用 `wr do-submit \"<goal>\" --timeout-sec=1200`。"
        return {
            "success": False,
            "error": f"command_timeout:{normalized}:{timeout_value}s",
            "command": normalized,
            "timeout_sec": timeout_value,
            "hint": hint,
        }

    def _build_command_exception_payload(self, command: str, exc: Exception) -> Dict[str, Any]:
        message = self._compact_text(str(exc).strip() or exc.__class__.__name__, max_chars=1600)
        normalized_command = str(command or "").strip().lower()
        if (
            isinstance(exc, RuntimeError)
            and "runtime is unavailable" in message.lower()
        ) or "install optional dependencies from requirements.txt" in message.lower():
            skills_cmd = build_cli_command('skills --resolve "<goal>" --compact')
            do_plan_cmd = build_cli_command('do-plan "<goal>"')
            dry_run_cmd = build_cli_command('do "<goal>" --dry-run')
            return {
                "success": False,
                "error": "runtime_unavailable",
                "command": normalized_command or command,
                "detail": message,
                "hint": (
                    f"先执行 `{build_cli_command('doctor')}` 检查缺失依赖。"
                    f"如需先让 AI 规划任务，可继续使用 "
                    f"`{skills_cmd}`、"
                    f"`{do_plan_cmd}`、"
                    f"`{dry_run_cmd}`。"
                ),
            }
        return {
            "success": False,
            "error": f"unexpected_command_error:{normalized_command or command}",
            "detail": message,
        }

    async def stop(self, show_farewell: bool = True):
        """停止"""
        if self.agent:
            await self.agent.close()
        if self.tools:
            await self.tools.close()
        if not show_farewell:
            return
        if self._console:
            self._console.print("Bye 再见!", style="bold green")
        else:
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
                self._print_usage("用法：do <goal> [--skill=name] [--dry-run] [--strict] [--js] [--top=N] [--crawl-assist] [--crawl-pages=N] [--command-timeout-sec=N] [--html-first|--no-html-first]")
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
                self._print_usage("用法：do-plan <goal> [--skill=name] [--strict] [--js] [--top=N] [--crawl-assist] [--crawl-pages=N] [--html-first|--no-html-first]")
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
                self._print_usage("用法：do-submit <goal> [--skill=name] [--strict] [--js] [--top=N] [--crawl-assist] [--crawl-pages=N] [--timeout-sec=N] [--html-first|--no-html-first]")
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
                        f"wr job-status {job['id']}",
                        f"wr job-result {job['id']}",
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

        elif command in {"jobs-clean", "jobs_clean", "job-clean", "job_clean"}:
            keep_recent = 120
            older_than_days: Optional[int] = None
            include_running = False
            i = 0
            while i < len(args):
                arg = args[i]
                if arg.startswith("--keep="):
                    keep_recent = self._parse_option_int(arg.split("=", 1)[1], keep_recent)
                elif arg == "--keep" and i + 1 < len(args):
                    i += 1
                    keep_recent = self._parse_option_int(args[i], keep_recent)
                elif arg.startswith("--days="):
                    older_than_days = self._parse_option_int(arg.split("=", 1)[1], 14)
                elif arg == "--days" and i + 1 < len(args):
                    i += 1
                    older_than_days = self._parse_option_int(args[i], 14)
                elif arg == "--all":
                    include_running = True
                i += 1

            payload = self._job_store.cleanup_jobs(
                keep_recent=max(0, keep_recent),
                older_than_days=older_than_days,
                include_running=include_running,
            )
            self._print_result(
                {
                    "success": True,
                    "cleanup": payload,
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
                self._print_usage("用法：ir-lint <ir-file|json|workflow-file|workflow-json>")
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
                self._print_usage("用法：quick <url|query> [--js] [--top=N] [--html-first|--no-html-first] [--crawl-assist] [--crawl-pages=N] [--strict] [--legacy] [--command-timeout-sec=N]")
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
                self._print_usage("用法：task <goal> [--js] [--top=N] [--html-first|--no-html-first] [--crawl-assist] [--crawl-pages=N] [--strict] [--command-timeout-sec=N]")
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
                self._print_usage("用法：search <query> [url]")
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
                self._print_usage("用法：web <query> [--no-crawl] [--crawl-pages=N] [--num-results=N] [--engine=name|a,b]")
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
                self._print_usage("用法：mindsearch <query> [--turns=N] [--branches=N] [--num-results=N] [--crawl=N] [--en] [--planner=name] [--strict-expand] [--news|--platforms|--commerce|--channel=x,y]")
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

        elif command in {"artifact", "artifacts", "graph"}:
            node_limit = 80
            edge_limit = 200
            node_kind: Optional[str] = None
            i = 0
            while i < len(args):
                arg = args[i]
                if arg.startswith("--nodes="):
                    node_limit = self._parse_option_int(arg.split("=", 1)[1], node_limit)
                elif arg == "--nodes" and i + 1 < len(args):
                    i += 1
                    node_limit = self._parse_option_int(args[i], node_limit)
                elif arg.startswith("--edges="):
                    edge_limit = self._parse_option_int(arg.split("=", 1)[1], edge_limit)
                elif arg == "--edges" and i + 1 < len(args):
                    i += 1
                    edge_limit = self._parse_option_int(args[i], edge_limit)
                elif arg.startswith("--kind="):
                    node_kind = arg.split("=", 1)[1].strip() or None
                elif arg == "--kind" and i + 1 < len(args):
                    i += 1
                    node_kind = args[i].strip() or None
                i += 1

            snapshot = self.agent.get_artifact_graph_snapshot(
                node_limit=node_limit,
                edge_limit=edge_limit,
                node_kind=node_kind,
            )
            self._print_result({"success": True, "artifact_graph": snapshot})

        elif command in {"events", "runtime-events", "runtime_events"}:
            limit = 50
            event_type: Optional[str] = None
            source: Optional[str] = None
            since_seq: Optional[int] = None
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
                elif arg.startswith("--source="):
                    source = arg.split("=", 1)[1].strip() or None
                elif arg == "--source" and i + 1 < len(args):
                    i += 1
                    source = args[i].strip() or None
                elif arg.startswith("--since="):
                    since_seq = self._parse_option_int(arg.split("=", 1)[1], 0)
                elif arg == "--since" and i + 1 < len(args):
                    i += 1
                    since_seq = self._parse_option_int(args[i], 0)
                i += 1

            snapshot = self.agent.get_runtime_events_snapshot(
                limit=limit,
                event_type=event_type,
                source=source,
                since_seq=since_seq,
            )
            self._print_result({"success": True, "runtime_events": snapshot})

        elif command in {"pressure", "runtime-pressure", "runtime_pressure"}:
            refresh = "--no-refresh" not in args
            snapshot = self.agent.get_runtime_pressure_snapshot(refresh=refresh)
            self._print_result({"success": True, "runtime_pressure": snapshot})

        elif command in {"telemetry", "budget", "budget-telemetry", "budget_telemetry"}:
            refresh = "--no-refresh" not in args
            snapshot = self.agent.get_budget_telemetry_snapshot(refresh=refresh)
            self._print_result({"success": True, "budget_telemetry": snapshot})

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
                self._print_usage("用法：auth-hint <url>")
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
                self._print_usage("用法：workflow <spec-file|json> [--var key=value] [--set key=value] [--strict] [--dry-run]")
                self._print_line("示例：workflow .web-rooter/workflow.social.json --var topic='AI Agent 评论' --var top_hits=8", level="dim")
                self._print_line("先生成模板：workflow-template .web-rooter/workflow.social.json --scenario=social_comments --force", level="dim")
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

            effective_spec = deepcopy(spec)
            if overrides:
                variables = effective_spec.setdefault("variables", {})
                if not isinstance(variables, dict):
                    variables = {}
                    effective_spec["variables"] = variables
                self._merge_nested_dict(variables, overrides)

            workflow_ir = build_command_ir(
                command="workflow",
                goal=f"workflow:{effective_spec.get('name', 'adhoc')}",
                route="auto",
                workflow_spec=effective_spec,
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
                self._print_usage("用法：academic <query> [--papers-only|--with-code] [--no-abstracts] [--num-results=N] [--source=arxiv]")
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
                self._print_usage("用法：deep <query> [--en] [--crawl=N] [--num-results=N] [--variants=N] [--engine=name|a,b] [--news] [--platforms] [--commerce] [--channel=x,y]")
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
                self._print_usage("用法：social <query> [--platform=xiaohongshu|zhihu|tieba|douyin|bilibili|weibo|reddit|twitter]")
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
                self._print_usage("用法：shopping <query> [--platform=taobao|jd|pinduoduo|meituan]")
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
                self._print_usage("用法：tech <query> [--source=github] [--source=stackoverflow]")
                return True

            logger.info(f"搜索技术内容：{query}, 来源：{sources or '全部'}")
            result = await search_tech(query, sources or None)
            self._print_result(result)

        elif command == "export":
            if len(args) < 2:
                self._print_usage("用法：export <query> <output_file>")
                self._print_line("示例：export AI 新闻 output.json", level="dim")
            else:
                query = " ".join(args[:-1]).strip()
                output_file = args[-1]
                if not query:
                    self._print_line("Error: 查询词不能为空", level="error")
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
                self._print_line(f"结果已导出到：{output_file}", level="success")
                self._print_line(f"共 {result['total_results']} 条结果", level="info")

        elif command == "doctor":
            await self._run_doctor()

        elif command in {"update", "upgrade", "self-update", "self_update"}:
            payload = await self._run_update_command(args)
            self._print_result(payload)

        elif command == "help":
            self._print_help()

        elif command == "quit" or command == "exit":
            return False

        else:
            if self._looks_like_url(command):
                use_browser = "--js" in args
                url_parts = [command] + [a for a in args if not a.startswith("--")]
                url = " ".join(url_parts).strip()
                self._print_line(f"[提示] 未识别命令 '{command}'，检测为 URL，按 visit 执行。", level="warn")
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
                    self._print_line(f"[提示] 未识别命令 '{command}'，按智能模式执行。", level="warn")
                    await self._run_inferred_input(inferred_input, crawl_pages=crawl_pages)
                else:
                    self._print_line(f"Error: 未知命令：{command}", level="error")
                    self._print_line("输入 'help' 查看可用命令", level="dim")
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
                f"wr {suggestions[0]} ...",
                "wr do-plan \"<goal>\"",
                "wr do \"<goal>\"",
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
                        f'wr do-plan "{escaped_goal}" --skill={selected_skill}',
                        f'wr do "{escaped_goal}" --skill={selected_skill} --dry-run',
                        f'wr do "{escaped_goal}" --skill={selected_skill}',
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
    def _compact_text(value: str, max_chars: int = 1600) -> str:
        text = str(value or "").strip()
        if len(text) <= max_chars:
            return text
        if max_chars <= 16:
            return text[:max_chars]
        return text[: max_chars - 14].rstrip() + "...[truncated]"

    @classmethod
    def _build_truncated_output_payload(
        cls,
        render_target: Any,
        rendered: str,
        max_chars: int,
    ) -> Dict[str, Any]:
        preview_cap = max(240, min(2000, max_chars // 3))
        payload: Dict[str, Any] = {
            "success": None,
            "truncated": True,
            "output_limit_chars": max_chars,
            "output_original_chars": len(rendered),
            "hint": "Increase WEB_ROOTER_MAX_OUTPUT_CHARS to inspect full payload.",
            "preview": rendered[:preview_cap],
        }
        if isinstance(render_target, dict):
            payload["success"] = render_target.get("success")
            if "error" in render_target:
                payload["error"] = render_target.get("error")
            content = render_target.get("content")
            if isinstance(content, str) and content.strip():
                payload["content_preview"] = cls._compact_text(content, max_chars=600)
        return payload

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

    @classmethod
    def _merge_nested_dict(cls, target: Dict[str, Any], source: Dict[str, Any]) -> None:
        for key, value in source.items():
            if isinstance(value, dict):
                child = target.get(key)
                if not isinstance(child, dict):
                    child = {}
                    target[key] = child
                cls._merge_nested_dict(child, value)
            else:
                target[key] = deepcopy(value)

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

    async def _run_update_command(self, args: List[str]) -> Dict[str, Any]:
        """
        自更新命令：
        - wr update --check
        - wr update --list
        - wr update --to v0.2.4 --yes
        - wr update               (交互式选择版本)
        """
        env_repo = str(os.getenv("WEB_ROOTER_GITHUB_REPO", "")).strip()
        inferred_repo = infer_github_repo_from_git(Path.cwd(), remote="origin") or infer_github_repo_from_git(Path.cwd(), remote="github")
        repo = env_repo or inferred_repo or "baojiachen0214/web-rooter"
        include_prerelease = False
        check_only = False
        list_only = False
        yes = False
        force = False
        limit = 10
        target_tag: Optional[str] = None
        i = 0
        while i < len(args):
            arg = str(args[i]).strip()
            lower = arg.lower()
            if lower in {"--check", "-c"}:
                check_only = True
            elif lower in {"--list", "-l"}:
                list_only = True
            elif lower in {"--yes", "-y"}:
                yes = True
            elif lower == "--force":
                force = True
            elif lower in {"--prerelease", "--pre"}:
                include_prerelease = True
            elif lower.startswith("--repo="):
                repo = arg.split("=", 1)[1].strip() or repo
            elif lower == "--repo" and i + 1 < len(args):
                i += 1
                repo = str(args[i]).strip() or repo
            elif lower.startswith("--to="):
                target_tag = arg.split("=", 1)[1].strip() or None
            elif lower in {"--to", "-t"} and i + 1 < len(args):
                i += 1
                target_tag = str(args[i]).strip() or None
            elif lower.startswith("--limit="):
                limit = max(1, min(30, self._parse_option_int(arg.split("=", 1)[1], 10)))
            elif lower == "--limit" and i + 1 < len(args):
                i += 1
                limit = max(1, min(30, self._parse_option_int(str(args[i]), 10)))
            i += 1

        current_tag = f"v{APP_VERSION}"
        try:
            releases = await asyncio.to_thread(
                fetch_github_releases,
                repo,
                limit,
                include_prerelease,
            )
        except Exception as exc:
            token_present = bool(
                str(os.getenv("WEB_ROOTER_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or "").strip()
            )
            hint = None
            if "404" in str(exc) and not token_present:
                hint = "仓库可能为私有或不存在；可设置 WEB_ROOTER_GITHUB_TOKEN 后重试，或显式指定 --repo=owner/repo。"
            return {
                "success": False,
                "error": str(exc),
                "repo": repo,
                "current_version": current_tag,
                "hint": hint,
            }

        latest = select_latest_release(releases)
        latest_tag = latest.tag_name if latest else None
        cmp = compare_semver_tags(current_tag, latest_tag) if latest_tag else None

        if list_only:
            return {
                "success": True,
                "mode": "list",
                "repo": repo,
                "current_version": current_tag,
                "latest": (latest.to_dict() if latest else None),
                "releases": [item.to_dict() for item in releases],
            }

        if check_only:
            return {
                "success": True,
                "mode": "check",
                "repo": repo,
                "current_version": current_tag,
                "latest_version": latest_tag,
                "update_available": (cmp == 1 if cmp is not None else None),
                "latest_release": (latest.to_dict() if latest else None),
            }

        if not releases:
            return {
                "success": False,
                "error": "no_releases_found",
                "repo": repo,
                "current_version": current_tag,
            }

        if not target_tag:
            target_tag = latest_tag
            if not yes and sys.stdin.isatty():
                selected = self._prompt_select_release(releases)
                if selected is None:
                    return {
                        "success": False,
                        "error": "update_cancelled",
                        "repo": repo,
                        "current_version": current_tag,
                    }
                target_tag = selected

        if not target_tag:
            return {
                "success": False,
                "error": "target_tag_empty",
                "repo": repo,
            }

        if target_tag == current_tag:
            return {
                "success": True,
                "mode": "noop",
                "repo": repo,
                "message": f"当前已是目标版本：{current_tag}",
                "current_version": current_tag,
            }

        if not is_git_repo(Path.cwd()):
            return {
                "success": False,
                "error": "not_git_repo",
                "repo_root": str(Path.cwd()),
                "hint": "当前目录不是 git 仓库；请使用 release 包重新安装，或在源码仓库里执行 wr update。",
                "target_version": target_tag,
            }

        if not yes and sys.stdin.isatty():
            self._print_line(f"将仓库切换到 {target_tag}，是否继续？[y/N]", level="warn")
            confirm = input("> ").strip().lower()
            if confirm not in {"y", "yes"}:
                return {
                    "success": False,
                    "error": "update_cancelled",
                    "target_version": target_tag,
                }

        apply_result = await asyncio.to_thread(
            update_git_to_tag,
            Path.cwd(),
            target_tag,
            "origin",
            force,
        )
        apply_result["repo"] = repo
        apply_result["current_version"] = current_tag
        apply_result["target_version"] = target_tag
        if apply_result.get("success"):
            apply_result["next_steps"] = [
                "重新打开终端，执行 `wr --version` 确认版本。",
                "执行 `wr doctor` 检查运行环境。",
            ]
        return apply_result

    def _prompt_select_release(self, releases: List[Any]) -> Optional[str]:
        if not releases:
            return None

        items = releases[:10]
        if self._console and Table is not None:
            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("#", width=4)
            table.add_column("Tag", width=14)
            table.add_column("Published", width=12)
            table.add_column("Type", width=12)
            table.add_column("Name", overflow="fold")
            for idx, item in enumerate(items, 1):
                tag = str(getattr(item, "tag_name", "") or "")
                name = str(getattr(item, "name", "") or tag)
                published = str(getattr(item, "published_at", "") or "")[:10]
                prerelease = bool(getattr(item, "prerelease", False))
                typ = "pre-release" if prerelease else "stable"
                table.add_row(str(idx), tag, published, typ, name)
            self._console.print(table)
            self._print_line("输入版本序号（回车默认最新，q 取消）:", level="info")
        else:
            print("可选版本:")
            for idx, item in enumerate(items, 1):
                tag = str(getattr(item, "tag_name", "") or "")
                name = str(getattr(item, "name", "") or tag)
                published = str(getattr(item, "published_at", "") or "")[:10]
                prerelease = bool(getattr(item, "prerelease", False))
                typ = "pre-release" if prerelease else "stable"
                print(f"  {idx}. {tag} ({typ}, {published}) - {name}")
            print("输入版本序号（回车默认最新，q 取消）:")

        raw = input("> ").strip().lower()
        if raw in {"q", "quit", "cancel", "n", "no"}:
            return None
        if raw == "":
            return str(getattr(items[0], "tag_name", "") or "")
        idx = self._parse_option_int(raw, 1)
        idx = max(1, min(len(items), idx))
        return str(getattr(items[idx - 1], "tag_name", "") or "")

    async def _run_doctor(self):
        """运行本地环境诊断，减少 CLI 集成的试错成本。"""
        if self._console and Panel is not None:
            self._console.print(Panel.fit("Web-Rooter Doctor", border_style="cyan"))
        else:
            print("=" * 60)
            print("Web-Rooter Doctor")
            print("=" * 60)

        checks = []
        check_rows: List[Dict[str, Any]] = []

        def add_check(name: str, ok: bool, detail: str, fix: Optional[str] = None):
            checks.append(ok)
            marker = "OK" if ok else "FAIL"
            check_rows.append(
                {
                    "marker": marker,
                    "name": name,
                    "detail": detail,
                    "fix": fix if (fix and not ok) else "",
                }
            )
            if self._console is None:
                print(f"[{marker}] {name}: {detail}")
                if fix and not ok:
                    print(f"      修复建议: {fix}")

        def short_error(exc: Exception) -> str:
            message = str(exc).strip()
            if message:
                return message.splitlines()[0]
            return exc.__class__.__name__

        def http_failure_fix(detail: str) -> str:
            normalized = detail.upper()
            if "CERTIFICATE_VERIFY_FAILED" in normalized or "UNABLE TO GET LOCAL ISSUER CERTIFICATE" in normalized:
                return (
                    "若本机/代理使用自定义根证书，请设置 WEB_ROOTER_SSL_CA_FILE=/path/to/ca.pem；"
                    "若浏览器运行时可用，可尝试 visit <url> --js"
                )
            return "检查网络/DNS；若浏览器运行时可用，可尝试 visit <url> --js"

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

        add_check(
            "Web-Rooter 版本",
            APP_VERSION.startswith("0."),
            f"v{APP_VERSION}",
            "当前应保持 v0.x.x 版本线，待稳定后再进入 v1.0.0",
        )

        python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        add_check(
            "Python",
            sys.version_info >= (3, 10),
            f"{python_version} ({sys.executable})",
            (
                f"请升级到 Python 3.10+，或改用: {recommended_python} main.py doctor"
                if recommended_python
                else "请升级到 Python 3.10 或更高版本"
            ),
        )

        module_status: Dict[str, bool] = {}
        for module_name in ("aiohttp", "playwright", "mcp"):
            installed = importlib.util.find_spec(module_name) is not None
            module_status[module_name] = installed
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

        insecure_ssl_enabled = is_insecure_ssl_enabled()
        add_check(
            "TLS 证书校验",
            not insecure_ssl_enabled,
            "已启用证书校验" if not insecure_ssl_enabled else "已禁用证书校验（WEB_ROOTER_INSECURE_SSL=1）",
            "仅在可信内网或临时排障时使用；恢复后请移除 WEB_ROOTER_INSECURE_SSL",
        )

        if not module_status.get("aiohttp", False):
            add_check(
                "HTTP 抓取链路",
                False,
                "aiohttp 未安装，抓取链路未初始化",
                (
                    f"执行: {recommended_python} -m pip install aiohttp"
                    if recommended_python
                    else "执行: pip install aiohttp"
                ),
            )
        else:
            try:
                http_result = await asyncio.wait_for(
                    self.agent._crawler_fetch("https://example.com"),
                    timeout=12,
                )
                http_detail = (
                    f"status={http_result.status_code}"
                    if http_result.success
                    else (http_result.error or f"status={http_result.status_code}")
                )
                add_check(
                    "HTTP 抓取链路",
                    http_result.success,
                    http_detail,
                    http_failure_fix(http_detail),
                )
            except Exception as e:
                error_text = short_error(e)
                add_check(
                    "HTTP 抓取链路",
                    False,
                    error_text,
                    http_failure_fix(error_text),
                )

        success_count = sum(1 for ok in checks if ok)
        if self._console and Table is not None:
            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("状态", width=8)
            table.add_column("检查项", width=26)
            table.add_column("详情", overflow="fold")
            table.add_column("修复建议", overflow="fold")
            for row in check_rows:
                status = "PASS" if row["marker"] == "OK" else "FAIL"
                style = "green" if row["marker"] == "OK" else "red"
                table.add_row(
                    f"[{style}]{status}[/{style}]",
                    str(row["name"]),
                    str(row["detail"]),
                    str(row["fix"] or "-"),
                )
            self._console.print(table)
            summary_style = "bold green" if success_count == len(checks) else "bold yellow"
            self._console.print(
                f"诊断结果: {success_count}/{len(checks)} 通过",
                style=summary_style,
            )
            if success_count != len(checks):
                self._console.print("建议先完成 FAIL 项，再执行深度抓取任务。", style="yellow")
        else:
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
                render_target = self._build_truncated_output_payload(
                    render_target=render_target,
                    rendered=rendered,
                    max_chars=max_chars,
                )
                rendered = json.dumps(render_target, ensure_ascii=False, indent=2)
            if self._console and Syntax is not None and Panel is not None:
                syntax = Syntax(rendered, "json", word_wrap=True)
                status_ok = bool(render_target.get("success")) if isinstance(render_target, dict) and "success" in render_target else None
                if status_ok is True:
                    border = "green"
                    title = "Result · Success"
                elif status_ok is False:
                    border = "red"
                    title = "Result · Error"
                else:
                    border = "cyan"
                    title = "Result"
                self._console.print(Panel(syntax, title=title, border_style=border))
            elif self._console:
                self._console.print(rendered)
            else:
                print(rendered)
        else:
            if self._console:
                self._console.print(result)
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
  do <goal> [--skill=name] [--dry-run] [--strict] [--js] [--top=N] [--crawl-assist] [--crawl-pages=N] [--command-timeout-sec=N] [--html-first|--no-html-first]
                                  - 单入口：Intent -> Skill -> IR -> Lint -> Execute
  do-plan <goal> [--skill=name] [--strict] [--js] [--top=N] [--crawl-assist] [--crawl-pages=N] [--html-first|--no-html-first]
                                  - 先输出阶段化 skills 剧本与推荐 CLI 序列
  do-submit <goal> [--skill=name] [--strict] [--js] [--top=N] [--crawl-assist] [--crawl-pages=N] [--timeout-sec=N] [--html-first|--no-html-first]
                                  - 提交长任务到后台作业系统（非阻塞）
  quick <url|query> [--js] [--top=N] [--html-first|--no-html-first] [--crawl-assist] [--crawl-pages=N] [--strict] [--legacy] [--command-timeout-sec=N]
                                  - 默认智能入口（workflow 编排优先；--legacy 回退旧逻辑）
  task <goal> [--js] [--top=N] [--html-first|--no-html-first] [--crawl-assist] [--crawl-pages=N] [--strict] [--command-timeout-sec=N]
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
  jobs-clean [--keep=N] [--days=N] [--all]
                                  - 清理历史作业目录（默认只清理终态作业）
  job-status <job_id> [--with-result]
                                  - 查看作业状态（可附带结果）
  job-result <job_id>             - 读取作业结果
  safe-mode [status|on|off] [--policy=strict]
                                  - AI 命令防火墙（strict 模式只允许高层命令）
  update [--check|--list] [--to vX.Y.Z] [--yes] [--prerelease]
                                  - 连接 GitHub 检查/选择并更新本地版本（git 仓库）
  doctor                          - 环境自检（依赖/浏览器/抓取链路）
  [通用] --command-timeout-sec=N  - 覆盖单条命令超时（默认读取 WEB_ROOTER_COMMAND_TIMEOUT_SEC）
  context [--limit=N] [--event=type] - 查看全局深度抓取上下文事件
  artifact [--nodes=N] [--edges=N] [--kind=page|url|domain|request|session]
                                  - 查看运行时 artifact graph 快照（有预算上限）
  events [--limit=N] [--event=type] [--source=name] [--since=seq]
                                  - 查看运行时事件流快照（支持游标增量拉取）
  pressure [--no-refresh]         - 查看运行时压力级别与自适应降级限制
  telemetry [--no-refresh]        - 查看统一预算健康度（state/events/artifact/pressure）
  processors [--load=module:obj] [--force] - 查看/加载抓取后处理扩展
  planners [--load=module:obj] [--force] - 查看/加载 MindSearch planner 扩展
  challenge-profiles              - 查看 challenge workflow 路由档案
  auth-profiles                   - 查看本地登录态 profile
  auth-hint <url>                 - 查看指定站点登录态匹配与提示
  auth-template [path] [--force]  - 导出本地登录模板 JSON

【其他】
  --version                       - 显示版本
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
  jobs-clean --keep=80 --days=7
  job-status <job_id>
  job-result <job_id>
  safe-mode on --policy=strict
  quick https://example.com --js
  quick "WorldQuant alpha101 因子"
  quick "RAG benchmark 2026" --top=6 --html-first
  quick "RAG benchmark 2026" --top=6 --command-timeout-sec=90
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
  artifact --nodes=100 --edges=240 --kind=page
  events --event=visit_complete --limit=30
  events --since=120
  pressure
  telemetry
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
  update --check
  update --list
  update --to v0.2.1 --yes
  doctor
  # 也可直接输入 URL 或查询词（可疑命令拼写会先拦截并给建议）
  wr "https://example.com"
  wr "量化交易 因子 最新讨论"
"""
        if self._console and Panel is not None:
            self._console.print(
                Panel(
                    help_text.strip("\n"),
                    title="Web-Rooter CLI Help",
                    border_style="cyan",
                    expand=False,
                )
            )
        elif self._console:
            self._console.print(help_text)
        else:
            print(help_text)


async def interactive_mode():
    """交互模式"""
    cli = WebRooterCLI()
    await cli.start(show_banner=True)

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

            should_continue = await cli.run_command_safely(command, args)
            if not should_continue:
                break

    finally:
        await cli.stop(show_farewell=True)


async def command_mode(command: str, args: list[str]):
    """命令行模式"""
    cli = WebRooterCLI()
    await cli.start(show_banner=False)

    try:
        await cli.run_command_safely(command, args)
    finally:
        await cli.stop(show_farewell=False)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description=f"[Web]  Web-Rooter v{APP_VERSION} - AI Web Crawling Agent"
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
        "--version",
        action="version",
        version=f"web-rooter {APP_VERSION}",
    )

    parser.add_argument(
        "command",
        nargs="?",
        help="要执行的命令"
    )

    parser.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help="命令参数"
    )

    args = parser.parse_args()

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

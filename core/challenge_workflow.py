"""
挑战页动作编排模块（Scrapling + OpenClaw/IronClaw 思路的轻量实现）。

目标：
- 从“硬编码点击”升级为“可路由 + 可编排 + 可扩展” challenge workflow
- 内置 Cloudflare/通用挑战页 profile，并支持外部 JSON 扩展
- 保持 fail-open，不阻塞主抓取链路
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

try:
    from playwright.async_api import Page
except ModuleNotFoundError:  # pragma: no cover - optional runtime dependency
    Page = Any  # type: ignore[misc,assignment]

logger = logging.getLogger(__name__)


@dataclass
class ChallengeStep:
    """单个挑战动作步骤。"""

    type: str
    selector: Optional[str] = None
    selectors: List[str] = field(default_factory=list)
    text: Optional[str] = None
    timeout_ms: int = 1200
    wait_ms: int = 0
    frame_keywords: List[str] = field(default_factory=list)
    retries: int = 1
    distance_px: int = 260


@dataclass
class ChallengeProfile:
    """挑战动作 profile。"""

    name: str
    domains: List[str] = field(default_factory=list)
    markers: List[str] = field(default_factory=list)
    challenge_types: List[str] = field(default_factory=list)
    priority: int = 100
    steps: List[ChallengeStep] = field(default_factory=list)


def _default_profiles() -> Dict[str, ChallengeProfile]:
    """内置 profile。"""
    profiles: Dict[str, ChallengeProfile] = {}

    profiles["generic_challenge"] = ChallengeProfile(
        name="generic_challenge",
        priority=10,
        steps=[
            ChallengeStep(type="mouse_move"),
            ChallengeStep(type="scroll"),
            ChallengeStep(type="delay", wait_ms=700),
            ChallengeStep(
                type="click_any",
                selectors=[
                    "button:has-text('Verify')",
                    "button:has-text('Continue')",
                    "button:has-text('I am human')",
                    "button:has-text('I\\'m human')",
                    "button:has-text('继续')",
                    "button:has-text('验证')",
                    "[role='button']:has-text('Verify')",
                    "[role='button']:has-text('Continue')",
                    "input[type='checkbox'][name*='captcha' i]",
                    "input[type='checkbox'][id*='captcha' i]",
                    "input[type='checkbox'][name*='cf' i]",
                    "input[type='checkbox'][id*='cf' i]",
                ],
                timeout_ms=1600,
                retries=2,
            ),
            ChallengeStep(type="delay", wait_ms=1000),
            ChallengeStep(type="wait_challenge_disappear", timeout_ms=2400),
        ],
    )

    # Scrapling 检测思路：根据 cType/turnstile 脚本判断 Cloudflare 挑战类型。
    profiles["cloudflare_interstitial"] = ChallengeProfile(
        name="cloudflare_interstitial",
        markers=["just a moment", "verifying you are human", "cloudflare"],
        challenge_types=["non-interactive"],
        priority=230,
        steps=[
            ChallengeStep(type="delay", wait_ms=1200),
            ChallengeStep(type="wait_challenge_disappear", timeout_ms=6000),
        ],
    )

    profiles["cloudflare_turnstile"] = ChallengeProfile(
        name="cloudflare_turnstile",
        markers=["cloudflare", "turnstile", "challenge-platform", "verify you are human"],
        challenge_types=["managed", "interactive", "embedded"],
        priority=220,
        steps=[
            ChallengeStep(
                type="wait_selector",
                selector="iframe[src*='challenges.cloudflare.com'], #cf_turnstile, #cf-turnstile, .turnstile",
                timeout_ms=2200,
            ),
            ChallengeStep(
                type="click_iframe_center",
                selector="iframe[src*='challenges.cloudflare.com']",
                timeout_ms=2000,
                retries=2,
            ),
            ChallengeStep(
                type="click_locator_box",
                selectors=[
                    "#cf_turnstile div",
                    "#cf-turnstile div",
                    ".turnstile>div>div",
                    ".main-content p+div>div>div",
                ],
                timeout_ms=1800,
                retries=2,
            ),
            ChallengeStep(type="delay", wait_ms=900),
            ChallengeStep(type="wait_challenge_disappear", timeout_ms=5000),
        ],
    )

    profiles["frame_checkbox"] = ChallengeProfile(
        name="frame_checkbox",
        markers=["captcha", "recaptcha", "hcaptcha", "challenge", "cloudflare"],
        priority=160,
        steps=[
            ChallengeStep(
                type="frame_click_any",
                frame_keywords=["captcha", "recaptcha", "hcaptcha", "challenge", "cloudflare"],
                selectors=[
                    "#recaptcha-anchor",
                    "input[type='checkbox']",
                    "div[role='checkbox']",
                    "button",
                ],
                timeout_ms=1500,
                retries=2,
            ),
            ChallengeStep(type="delay", wait_ms=900),
            ChallengeStep(type="wait_challenge_disappear", timeout_ms=3500),
        ],
    )

    return profiles


def _normalize_text_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(x).strip().lower() for x in value if str(x).strip()]


def _load_custom_profiles_from_json(path: Path) -> Dict[str, ChallengeProfile]:
    """
    从 JSON 文件加载用户自定义 profile。

    结构示例：
    {
      "profiles": [
        {
          "name": "my_profile",
          "priority": 180,
          "domains": ["example.com"],
          "markers": ["cloudflare", "captcha"],
          "challenge_types": ["managed"],
          "steps": [
            {"type": "click", "selector": "button.verify", "timeout_ms": 1200},
            {"type": "delay", "wait_ms": 800}
          ]
        }
      ]
    }
    """
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("加载 challenge profile 失败 %s: %s", path, exc)
        return {}

    profiles_raw = payload.get("profiles", [])
    if not isinstance(profiles_raw, list):
        return {}

    profiles: Dict[str, ChallengeProfile] = {}
    for item in profiles_raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        steps_raw = item.get("steps", [])
        if not isinstance(steps_raw, list):
            continue

        steps: List[ChallengeStep] = []
        for step_raw in steps_raw:
            if not isinstance(step_raw, dict):
                continue
            step_type = str(step_raw.get("type", "")).strip()
            if not step_type:
                continue
            selectors = step_raw.get("selectors", []) or []
            frame_keywords = step_raw.get("frame_keywords", []) or []
            if not isinstance(selectors, list):
                selectors = []
            if not isinstance(frame_keywords, list):
                frame_keywords = []

            steps.append(
                ChallengeStep(
                    type=step_type,
                    selector=step_raw.get("selector"),
                    selectors=[str(x) for x in selectors if str(x).strip()],
                    text=step_raw.get("text"),
                    timeout_ms=int(step_raw.get("timeout_ms", 1200) or 1200),
                    wait_ms=int(step_raw.get("wait_ms", 0) or 0),
                    frame_keywords=[str(x).lower() for x in frame_keywords if str(x).strip()],
                    retries=max(1, int(step_raw.get("retries", 1) or 1)),
                    distance_px=int(step_raw.get("distance_px", 260) or 260),
                )
            )

        profiles[name] = ChallengeProfile(
            name=name,
            domains=_normalize_text_list(item.get("domains", [])),
            markers=_normalize_text_list(item.get("markers", [])),
            challenge_types=_normalize_text_list(item.get("challenge_types", [])),
            priority=int(item.get("priority", 100) or 100),
            steps=steps,
        )

    return profiles


class ChallengeWorkflowRunner:
    """挑战动作执行器（注册式 profile 路由 + 编排执行）。"""

    _DEFAULT_MARKERS = [
        "captcha",
        "recaptcha",
        "hcaptcha",
        "cloudflare",
        "challenge",
        "verify you are human",
        "unusual traffic",
        "access denied",
        "just a moment",
        "verifying you are human",
        "turnstile",
        "slider",
        "slide to verify",
        "please verify",
        "login required",
        "sign in to continue",
        "人机验证",
        "安全验证",
        "滑块",
        "验证码",
        "登录后查看",
        "访问受限",
    ]

    def __init__(self):
        self._profiles = _default_profiles()
        self._profile_sources: Dict[str, str] = {name: "builtin" for name in self._profiles}
        self._loaded_custom_paths: set[Path] = set()
        self._load_custom_profiles_if_needed()

    def _discover_profile_paths(self) -> List[Path]:
        project_root = Path(__file__).resolve().parent.parent
        default_dirs: List[Path] = [
            project_root / "profiles" / "challenge_profiles",
            Path.home() / ".web-rooter" / "challenge-profiles",
        ]
        file_paths: List[Path] = []
        seen: set[Path] = set()

        def add_file(path: Path) -> None:
            resolved = path.expanduser().resolve()
            if resolved in seen or not resolved.exists() or not resolved.is_file():
                return
            seen.add(resolved)
            file_paths.append(resolved)

        def add_dir(path: Path) -> None:
            resolved_dir = path.expanduser().resolve()
            if not resolved_dir.exists() or not resolved_dir.is_dir():
                return
            for item in sorted(resolved_dir.glob("*.json")):
                add_file(item)

        for default_dir in default_dirs:
            add_dir(default_dir)

        profile_dir_env = os.getenv("WEB_ROOTER_CHALLENGE_PROFILE_DIR", "").strip()
        if profile_dir_env:
            for raw_dir in profile_dir_env.split(os.pathsep):
                if raw_dir.strip():
                    add_dir(Path(raw_dir.strip()))

        profile_file_env = os.getenv("WEB_ROOTER_CHALLENGE_PROFILE_FILE", "").strip()
        if profile_file_env:
            for raw_file in profile_file_env.split(os.pathsep):
                if raw_file.strip():
                    add_file(Path(raw_file.strip()))

        return file_paths

    def _load_custom_profiles_if_needed(self, force: bool = False) -> None:
        file_paths = self._discover_profile_paths()

        for path in file_paths:
            if not force and path in self._loaded_custom_paths:
                continue
            custom = _load_custom_profiles_from_json(path)
            if custom:
                self._profiles.update(custom)
                for name in custom:
                    self._profile_sources[name] = str(path)
                logger.info("已加载 %d 个自定义 challenge profiles: %s", len(custom), path)
            self._loaded_custom_paths.add(path)

    def list_profiles(self) -> List[str]:
        return [
            name
            for name, _ in sorted(
                self._profiles.items(),
                key=lambda item: item[1].priority,
                reverse=True,
            )
        ]

    def describe_profiles(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for profile in sorted(self._profiles.values(), key=lambda item: item.priority, reverse=True):
            rows.append(
                {
                    "name": profile.name,
                    "source": self._profile_sources.get(profile.name, "builtin"),
                    "priority": profile.priority,
                    "domains": profile.domains,
                    "markers": profile.markers,
                    "challenge_types": profile.challenge_types,
                    "steps": len(profile.steps),
                }
            )
        return rows

    def select_profiles(
        self,
        url: str,
        detectors: Optional[Sequence[str]] = None,
        page_signals: str = "",
        challenge_type: Optional[str] = None,
        forced_profile: Optional[str] = None,
    ) -> List[ChallengeProfile]:
        self._load_custom_profiles_if_needed()

        if forced_profile:
            chosen = self._profiles.get(forced_profile)
            if chosen:
                return [chosen]

        host = (urlparse(url).hostname or "").lower()
        detector_text = " ".join([str(x).lower() for x in list(detectors or []) if str(x).strip()])
        merged_signals = f"{page_signals.lower()} {detector_text}".strip()

        scored: List[Tuple[int, ChallengeProfile]] = []
        for profile in self._profiles.values():
            score = int(profile.priority)
            if host and profile.domains:
                if any(host == domain or host.endswith("." + domain) for domain in profile.domains):
                    score += 180
                else:
                    score -= 20

            if challenge_type:
                if profile.challenge_types and challenge_type in profile.challenge_types:
                    score += 220
                elif profile.challenge_types:
                    score -= 40

            if profile.markers and merged_signals:
                marker_hits = sum(1 for marker in profile.markers if marker and marker in merged_signals)
                score += marker_hits * 55

            if profile.name == "generic_challenge":
                score -= 120

            scored.append((score, profile))

        scored.sort(key=lambda item: (item[0], item[1].priority), reverse=True)
        selected = [profile for _, profile in scored]

        # generic 兜底始终保留末尾
        generic = self._profiles.get("generic_challenge")
        if generic:
            selected = [p for p in selected if p.name != generic.name] + [generic]

        return selected

    async def run(
        self,
        page: Page,
        url: str,
        detectors: Optional[List[str]] = None,
        profile_name: Optional[str] = None,
        max_rounds: int = 2,
        max_profiles: int = 3,
    ) -> Dict[str, Any]:
        """执行动作流并返回报告。"""
        signals = await self._collect_page_signals(page)
        challenge_type = await self._detect_cloudflare_challenge_type(page, preloaded_signals=signals)
        candidates = self.select_profiles(
            url=url,
            detectors=detectors,
            page_signals=signals,
            challenge_type=challenge_type,
            forced_profile=profile_name,
        )

        report: Dict[str, Any] = {
            "profile": None,
            "profiles_considered": [item.name for item in candidates[: max(1, max_profiles)]],
            "profiles_tried": [],
            "challenge_type": challenge_type,
            "url": url,
            "rounds": 0,
            "steps_attempted": 0,
            "step_success": 0,
            "errors": [],
            "resolved": False,
        }

        loop_rounds = max(1, max_rounds)
        loop_profiles = max(1, max_profiles)
        for round_idx in range(loop_rounds):
            report["rounds"] = round_idx + 1
            current_profiles = candidates[:loop_profiles]
            for profile in current_profiles:
                if profile.name not in report["profiles_tried"]:
                    report["profiles_tried"].append(profile.name)
                for step in profile.steps:
                    report["steps_attempted"] += 1
                    try:
                        ok = await self._execute_step(page, step, detectors=detectors)
                        if ok:
                            report["step_success"] += 1
                    except Exception as exc:
                        report["errors"].append(f"{profile.name}:{step.type}:{exc}")

                if not await self._is_challenged(page, detectors):
                    report["resolved"] = True
                    report["profile"] = profile.name
                    return report

            if round_idx < loop_rounds - 1:
                await asyncio.sleep(0.45)
                signals = await self._collect_page_signals(page)
                challenge_type = await self._detect_cloudflare_challenge_type(
                    page,
                    preloaded_signals=signals,
                )
                report["challenge_type"] = challenge_type
                candidates = self.select_profiles(
                    url=url,
                    detectors=detectors,
                    page_signals=signals,
                    challenge_type=challenge_type,
                    forced_profile=profile_name,
                )

        return report

    async def _execute_step(
        self,
        page: Page,
        step: ChallengeStep,
        detectors: Optional[List[str]] = None,
    ) -> bool:
        max_attempts = max(1, int(step.retries or 1))
        last_error: Optional[Exception] = None

        for attempt in range(max_attempts):
            try:
                return await self._execute_step_once(page, step, detectors=detectors)
            except Exception as exc:
                last_error = exc
                if attempt < max_attempts - 1:
                    await asyncio.sleep(0.18 * (attempt + 1))

        if last_error:
            raise last_error
        return False

    async def _execute_step_once(
        self,
        page: Page,
        step: ChallengeStep,
        detectors: Optional[List[str]] = None,
    ) -> bool:
        step_type = step.type.strip().lower()
        timeout = max(300, step.timeout_ms)

        if step.wait_ms > 0:
            await asyncio.sleep(step.wait_ms / 1000)

        if step_type == "delay":
            wait_ms = step.wait_ms if step.wait_ms > 0 else random.randint(500, 1200)
            await asyncio.sleep(wait_ms / 1000)
            return True

        if step_type == "mouse_move":
            await page.mouse.move(random.randint(40, 880), random.randint(40, 640))
            return True

        if step_type == "scroll":
            await page.evaluate("window.scrollBy(0, Math.floor(150 + Math.random() * 500));")
            return True

        if step_type == "wait_selector":
            selectors = [step.selector] if step.selector else []
            selectors.extend(step.selectors)
            for selector in [s for s in selectors if s]:
                try:
                    await page.wait_for_selector(selector, timeout=timeout)
                    return True
                except Exception:
                    continue
            return False

        if step_type in {"drag_slider", "drag_slider_any"}:
            selectors = [s for s in ([step.selector] + step.selectors) if s]
            if not selectors:
                selectors = [
                    "[class*='slider' i]",
                    "[id*='slider' i]",
                    "[class*='verify' i] [role='slider']",
                    "div[role='slider']",
                ]
            distance = max(80, min(420, int(step.distance_px or 260)))
            for selector in selectors:
                locator = page.locator(selector).first
                try:
                    if await locator.count() <= 0:
                        continue
                    if not await locator.is_visible(timeout=timeout):
                        continue
                    box = await locator.bounding_box()
                    if not box:
                        continue
                    start_x = box["x"] + min(max(8.0, box["width"] * 0.2), 28.0)
                    start_y = box["y"] + (box["height"] / 2) + random.uniform(-1.5, 1.5)
                    end_x = start_x + distance + random.uniform(-10.0, 10.0)
                    end_y = start_y + random.uniform(-2.0, 2.0)
                    await page.mouse.move(start_x, start_y)
                    await asyncio.sleep(random.uniform(0.06, 0.12))
                    await page.mouse.down()
                    await page.mouse.move(end_x, end_y, steps=random.randint(16, 28))
                    await asyncio.sleep(random.uniform(0.03, 0.12))
                    await page.mouse.up()
                    return True
                except Exception:
                    continue
            return False

        if step_type == "click" and step.selector:
            return await self._click_locator(page, step.selector, timeout=timeout)

        if step_type == "click_any":
            for selector in [s for s in step.selectors if s]:
                if await self._click_locator(page, selector, timeout=timeout):
                    return True
            return False

        if step_type == "click_iframe_center":
            iframe_selector = step.selector or "iframe[src*='challenges.cloudflare.com']"
            iframe = page.locator(iframe_selector).first
            if await iframe.count() <= 0:
                return False
            if not await iframe.is_visible(timeout=timeout):
                return False
            box = await iframe.bounding_box()
            if not box:
                return False
            await page.mouse.click(
                box["x"] + box["width"] / 2 + random.uniform(-3.0, 3.0),
                box["y"] + box["height"] / 2 + random.uniform(-3.0, 3.0),
                delay=random.randint(90, 210),
            )
            return True

        if step_type == "click_locator_box":
            selectors = [s for s in ([step.selector] + step.selectors) if s]
            for selector in selectors:
                locator = page.locator(selector).first
                try:
                    if await locator.count() <= 0:
                        continue
                    if not await locator.is_visible(timeout=timeout):
                        continue
                    box = await locator.bounding_box()
                    if not box:
                        continue
                    await page.mouse.click(
                        box["x"] + (box["width"] / 2) + random.uniform(-2.0, 2.0),
                        box["y"] + (box["height"] / 2) + random.uniform(-2.0, 2.0),
                        delay=random.randint(100, 220),
                    )
                    return True
                except Exception:
                    continue
            return False

        if step_type == "frame_click_any":
            frame_keywords = step.frame_keywords or [
                "captcha",
                "recaptcha",
                "hcaptcha",
                "challenge",
                "cloudflare",
            ]
            for frame in page.frames:
                frame_url = (frame.url or "").lower()
                if not any(token in frame_url for token in frame_keywords):
                    continue
                for selector in step.selectors:
                    try:
                        locator = frame.locator(selector).first
                        if await locator.count() <= 0:
                            continue
                        if not await locator.is_visible(timeout=timeout):
                            continue
                        await locator.click(timeout=timeout, force=True)
                        return True
                    except Exception:
                        continue
            return False

        if step_type == "wait_challenge_disappear":
            deadline = asyncio.get_running_loop().time() + max(0.6, timeout / 1000.0)
            while asyncio.get_running_loop().time() < deadline:
                if not await self._is_challenged(page, detectors):
                    return True
                await asyncio.sleep(0.25)
            return False

        if step_type == "wait_title_not_contains" and step.text:
            marker = step.text.lower()
            deadline = asyncio.get_running_loop().time() + max(0.5, timeout / 1000.0)
            while asyncio.get_running_loop().time() < deadline:
                try:
                    title = (await page.title()).lower()
                except Exception:
                    title = ""
                if marker not in title:
                    return True
                await asyncio.sleep(0.2)
            return False

        if step_type == "wait_url_not_contains" and step.text:
            marker = step.text.lower()
            deadline = asyncio.get_running_loop().time() + max(0.5, timeout / 1000.0)
            while asyncio.get_running_loop().time() < deadline:
                current = (page.url or "").lower()
                if marker not in current:
                    return True
                await asyncio.sleep(0.2)
            return False

        if step_type == "press" and step.text:
            await page.keyboard.press(step.text)
            return True

        if step_type == "evaluate" and step.text:
            await page.evaluate(step.text)
            return True

        if step_type == "type" and step.selector and step.text is not None:
            locator = page.locator(step.selector).first
            if await locator.count() <= 0:
                return False
            await locator.fill(step.text, timeout=timeout)
            return True

        return False

    async def _click_locator(self, page: Page, selector: str, timeout: int) -> bool:
        locator = page.locator(selector).first
        if await locator.count() <= 0:
            return False
        if not await locator.is_visible(timeout=timeout):
            return False
        await locator.click(timeout=timeout, force=True)
        return True

    async def _collect_page_signals(self, page: Page) -> str:
        try:
            title = (await page.title()).lower()
        except Exception:
            title = ""

        current_url = (page.url or "").lower()
        try:
            body_text = await page.evaluate(
                "() => (document.body && document.body.innerText ? document.body.innerText.slice(0, 5000) : '')"
            )
            body_text = (body_text or "").lower()
        except Exception:
            body_text = ""

        return f"{title}\n{current_url}\n{body_text}"

    async def _detect_cloudflare_challenge_type(
        self,
        page: Page,
        preloaded_signals: str = "",
    ) -> Optional[str]:
        try:
            html = await page.evaluate(
                "() => (document.documentElement && document.documentElement.outerHTML "
                "? document.documentElement.outerHTML.slice(0, 120000) : '')"
            )
            html = (html or "").lower()
        except Exception:
            html = ""

        if html:
            matched = re.search(r"ctype\s*[:=]\s*['\"]([a-z\\-]+)['\"]", html)
            if matched:
                return matched.group(1).lower()

            if "challenges.cloudflare.com/turnstile/v" in html:
                return "embedded"

            if "challenge-platform" in html and "turnstile" in html:
                return "managed"

        signals = preloaded_signals.lower() if preloaded_signals else await self._collect_page_signals(page)
        if "just a moment" in signals or "verifying you are human" in signals:
            return "non-interactive"
        if "turnstile" in signals:
            return "managed"
        return None

    async def _is_challenged(self, page: Page, detectors: Optional[List[str]] = None) -> bool:
        if page.is_closed():
            return True

        for selector in list(detectors or []):
            try:
                locator = page.locator(selector).first
                if await locator.count() > 0 and await locator.is_visible(timeout=500):
                    return True
            except Exception:
                continue

        merged = await self._collect_page_signals(page)
        return any(marker in merged for marker in self._DEFAULT_MARKERS)


_runner: Optional[ChallengeWorkflowRunner] = None


def get_challenge_workflow_runner() -> ChallengeWorkflowRunner:
    global _runner
    if _runner is None:
        _runner = ChallengeWorkflowRunner()
    return _runner

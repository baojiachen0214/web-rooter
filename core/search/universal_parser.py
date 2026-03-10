"""
通用结果解析器 - 解析任何搜索引擎的搜索结果

设计原则（第一性原理）：
1. 搜索结果本质是“可点击外部链接 + 可读标题 + 简短上下文”。
2. 引擎页面结构会频繁变化，选择器只应作为“优先策略”，不能是唯一策略。
3. 所有解析结果都要统一标准化、校验和去重，减少上层补丁复杂度。
"""
from __future__ import annotations

import re
from typing import List, Dict, Any, Optional
from urllib.parse import parse_qs, unquote, urljoin, urlparse, urlunparse

from playwright.async_api import Page
import logging

logger = logging.getLogger(__name__)


class UniversalResultParser:
    """
    通用搜索结果解析器

    能力：
    - 选择器优先解析（配置驱动）
    - 通用候选提取兜底（DOM 全局扫描）
    - 链接标准化（相对链接、跳转链接、fragment 清理）
    - 去重和噪声过滤（搜索引擎站内导航、空标题、无效链接）
    """

    def __init__(self, engine_config: Any):
        self.config = engine_config
        self.selectors = engine_config.selectors if hasattr(engine_config, "selectors") else {}
        self.fallback_selector = (
            getattr(engine_config, "fallbackSelector", None)
            or 'div:has(a[href*="http"])'
        )
        self.link_validation = (
            getattr(engine_config, "linkValidation", None)
            or ["http"]
        )

    async def parse_results(
        self,
        page: Page,
        limit: int = 10,
    ) -> List[Dict[str, str]]:
        """
        解析搜索结果。
        先尝试配置化容器解析，不足时降级到通用候选扫描。
        """
        limit = max(1, limit)
        results: List[Dict[str, str]] = []
        seen_links = set()

        try:
            if await self._is_challenge_page(page):
                logger.warning("检测到挑战页，跳过结果解析：%s", page.url)
                return []

            # 阶段 1：按配置选择器提取
            result_containers = await self._find_result_containers(page)
            if not result_containers and self.fallback_selector:
                logger.warning(
                    "未找到配置结果容器，尝试备用选择器：%s",
                    self.fallback_selector,
                )
                try:
                    result_containers = await page.query_selector_all(self.fallback_selector)
                except Exception as exc:
                    logger.debug("备用选择器失败: %s", exc)
                    result_containers = []

            logger.info("找到 %s 个结果容器", len(result_containers))
            for container in result_containers:
                parsed = await self._parse_result_container(container, page.url)
                if not parsed or not self._validate_result(parsed, page.url):
                    continue
                dedupe_key = self._dedupe_key(parsed["link"])
                if dedupe_key in seen_links:
                    continue
                seen_links.add(dedupe_key)
                results.append(parsed)
                if len(results) >= limit:
                    return results

            # 阶段 2：通用兜底扫描（选择器漂移时保证召回）
            fallback_candidates = await self._extract_generic_candidates(page, limit * 8)
            for candidate in fallback_candidates:
                if not self._validate_result(candidate, page.url):
                    continue
                dedupe_key = self._dedupe_key(candidate["link"])
                if dedupe_key in seen_links:
                    continue
                seen_links.add(dedupe_key)
                results.append(candidate)
                if len(results) >= limit:
                    break

        except Exception as exc:
            logger.error("解析搜索结果失败：%s", exc)

        return results

    async def _is_challenge_page(self, page: Page) -> bool:
        """页面级挑战识别，避免把验证页中的帮助链接误当作搜索结果。"""
        try:
            title = (await page.title() or "").strip().lower()
        except Exception:
            title = ""

        try:
            body_text = await page.evaluate(
                "() => (document && document.body && document.body.innerText) ? document.body.innerText.slice(0, 3000) : ''"
            )
        except Exception:
            body_text = ""

        text = f"{title} {body_text} {page.url}".lower()
        challenge_markers = [
            "captcha",
            "recaptcha",
            "verify you are human",
            "human verification",
            "unusual traffic",
            "cloudflare",
            "cf-challenge",
            "just a moment",
            "安全验证",
            "百度安全验证",
            "ç¾åº¦å®å¨éªè¯",
            "人机验证",
            "请输入验证码",
            "检测到异常流量",
            "访问受限",
            "blocked",
        ]
        return any(marker in text for marker in challenge_markers)

    async def _find_result_containers(self, page: Page) -> List[Any]:
        if not self.selectors:
            return []

        raw_selector = self.selectors.get("resultContainer", "")
        if not raw_selector:
            return []

        for selector in self._split_selectors(raw_selector):
            try:
                containers = await page.query_selector_all(selector)
                if containers:
                    logger.info("使用选择器 '%s' 找到 %s 个结果", selector, len(containers))
                    return containers
            except Exception as exc:
                logger.debug("选择器 '%s' 失败：%s", selector, exc)

        return []

    async def _parse_result_container(self, container: Any, page_url: str) -> Optional[Dict[str, str]]:
        """解析单个结果容器。"""
        try:
            title_selector = self.selectors.get("title", "")
            link_selector = self.selectors.get("link", "")
            snippet_selector = self.selectors.get("snippet", "")

            title = await self._extract_text(container, title_selector)
            link = await self._extract_href(container, link_selector)
            snippet = await self._extract_text(container, snippet_selector)

            # 兜底：若未命中配置链接，取容器内首个 a[href]
            if not link:
                anchor = await container.query_selector("a[href]")
                if anchor:
                    link = (await anchor.get_attribute("href")) or ""
                    if not title:
                        title = (await anchor.text_content()) or ""

            normalized_link = self._normalize_link(link, page_url)
            if not normalized_link:
                return None

            cleaned_title = self._clean_text(title)
            if not cleaned_title:
                # 兜底：用 URL 最后段作为弱标题，避免空标题直接丢弃有效结果
                parsed = urlparse(normalized_link)
                tail = parsed.path.rstrip("/").split("/")[-1]
                cleaned_title = self._clean_text(tail or parsed.netloc)

            return {
                "title": cleaned_title[:200],
                "link": normalized_link,
                "snippet": self._clean_text(snippet)[:500],
            }
        except Exception as exc:
            logger.debug("解析结果容器失败：%s", exc)
            return None

    async def _extract_text(self, container: Any, selector: str) -> str:
        if not selector:
            return ""

        for sel in self._split_selectors(selector):
            try:
                element = await container.query_selector(sel)
                if element:
                    text = await element.text_content()
                    if text and text.strip():
                        return text
            except Exception:
                continue
        return ""

    async def _extract_href(self, container: Any, selector: str) -> str:
        if not selector:
            return ""

        for sel in self._split_selectors(selector):
            try:
                element = await container.query_selector(sel)
                if element:
                    href = await element.get_attribute("href")
                    if href and href.strip():
                        return href
            except Exception:
                continue
        return ""

    async def _extract_generic_candidates(self, page: Page, max_candidates: int) -> List[Dict[str, str]]:
        """
        通用兜底提取：
        - 扫描所有 a[href]
        - 使用附近容器文本作为摘要
        - 在 Python 侧再做标准化和过滤
        """
        try:
            raw_candidates = await page.evaluate(
                """(maxCandidates) => {
                    const out = [];
                    const anchors = Array.from(document.querySelectorAll("a[href]"));
                    const pickSnippet = (anchor) => {
                        const block = anchor.closest("article, li, div, section") || anchor.parentElement;
                        if (!block) return "";
                        const raw = (block.innerText || "").replace(/\\s+/g, " ").trim();
                        if (!raw) return "";
                        return raw.slice(0, 500);
                    };
                    for (const a of anchors) {
                        if (out.length >= maxCandidates) break;
                        const href = (a.getAttribute("href") || "").trim();
                        if (!href) continue;
                        if (href.startsWith("#") || href.startsWith("javascript:") || href.startsWith("mailto:") || href.startsWith("tel:")) continue;

                        const text = ((a.innerText || a.textContent || a.getAttribute("title") || "").trim());
                        if (!text) continue;

                        out.push({
                            title: text,
                            link: href,
                            snippet: pickSnippet(a),
                        });
                    }
                    return out;
                }""",
                max_candidates,
            )
        except Exception as exc:
            logger.debug("通用候选提取失败：%s", exc)
            return []

        normalized: List[Dict[str, str]] = []
        seen = set()
        for item in raw_candidates or []:
            title = self._clean_text((item or {}).get("title", ""))
            link = self._normalize_link((item or {}).get("link", ""), page.url)
            snippet = self._clean_text((item or {}).get("snippet", ""))
            if not title or not link:
                continue
            key = self._dedupe_key(link)
            if key in seen:
                continue
            seen.add(key)
            normalized.append({
                "title": title[:200],
                "link": link,
                "snippet": snippet[:500],
            })
        return normalized

    def _validate_result(self, result: Dict[str, str], page_url: str) -> bool:
        link = result.get("link", "")
        title = result.get("title", "")
        snippet = result.get("snippet", "")

        if not link or not title:
            return False

        if self._looks_like_challenge_page(link, title, snippet):
            return False

        if self._looks_like_engine_navigation(link, page_url):
            return False

        # 链接验证规则（配置优先）
        if self.link_validation:
            link_lower = link.lower()
            if not any(pattern.lower() in link_lower for pattern in self.link_validation):
                return False

        parsed = urlparse(link)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _looks_like_challenge_page(link: str, title: str, snippet: str) -> bool:
        """过滤反爬验证页（captcha / unusual traffic / cloudflare challenge）。"""
        text = f"{title} {snippet} {link}".lower()
        challenge_keywords = [
            "captcha",
            "recaptcha",
            "verify",
            "human",
            "unusual traffic",
            "cloudflare",
            "cf-challenge",
            "blocked",
            "forbidden",
            "安全验证",
            "百度安全验证",
            "人机验证",
            "自动检测到",
            "服务条款",
            "sorry/index",
        ]
        if any(keyword in text for keyword in challenge_keywords):
            return True

        parsed = urlparse(link)
        host = parsed.netloc.lower()
        path = parsed.path.lower()
        title_lower = title.strip().lower()
        if host in {"support.google.com", "www.google.com"} and (
            "sorry" in path or title_lower in {"了解详情", "learn more"}
        ):
            return True
        return False

    @staticmethod
    def _split_selectors(selector: str) -> List[str]:
        return [s.strip() for s in (selector or "").split(",") if s.strip()]

    @staticmethod
    def _clean_text(text: Optional[str]) -> str:
        if not text:
            return ""
        text = re.sub(r"[\u200B-\u200D\uFEFF]", "", text)
        text = " ".join(text.split())
        return text.strip()

    def _normalize_link(self, href: str, page_url: str) -> str:
        """标准化链接并处理常见搜索引擎跳转 URL。"""
        raw = (href or "").strip()
        if not raw:
            return ""

        lower = raw.lower()
        if lower.startswith(("javascript:", "mailto:", "tel:", "#")):
            return ""

        # Google: /url?q=https://target...
        if raw.startswith("/url?") or raw.startswith("url?"):
            qs = parse_qs(raw.split("?", 1)[1] if "?" in raw else "")
            target = (qs.get("q") or qs.get("url") or [""])[0]
            if target:
                raw = unquote(target)

        # DuckDuckGo: https://duckduckgo.com/l/?uddg=...
        if "duckduckgo.com/l/?" in lower:
            parsed_ddg = urlparse(raw)
            uddg = parse_qs(parsed_ddg.query).get("uddg", [""])[0]
            if uddg:
                raw = unquote(uddg)

        absolute = urljoin(page_url, raw)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""

        # 去掉 fragment，降低重复
        cleaned = parsed._replace(fragment="")
        return urlunparse(cleaned)

    @staticmethod
    def _dedupe_key(link: str) -> str:
        parsed = urlparse(link or "")
        path = parsed.path or "/"
        if path != "/" and path.endswith("/"):
            path = path[:-1]
        return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}?{parsed.query}"

    @staticmethod
    def _looks_like_engine_navigation(link: str, page_url: str) -> bool:
        """
        过滤搜索引擎站内导航链接：
        - 同域且不在可疑跳转路径中（/url /link /l /redirect 等）基本视为导航噪声。
        """
        try:
            link_parsed = urlparse(link)
            page_parsed = urlparse(page_url)
            if not link_parsed.netloc or not page_parsed.netloc:
                return False

            if link_parsed.netloc.lower() != page_parsed.netloc.lower():
                return False

            path = (link_parsed.path or "").lower()
            redirect_markers = ["/url", "/link", "/l/", "/redirect", "/jump", "/out"]
            if any(marker in path for marker in redirect_markers):
                return False

            # 同域纯搜索页、设置页、登录页等通常不是目标结果
            nav_markers = ["/search", "/s", "/settings", "/preferences", "/account", "/login"]
            if any(path.startswith(marker) for marker in nav_markers):
                return True

            # 同域其它页面默认视为导航噪声，避免把引擎自身 UI 当结果
            return True
        except Exception:
            return False

    async def parse_with_javascript(self, page: Page) -> List[Dict[str, str]]:
        """
        兼容旧接口：直接走通用候选提取路径。
        """
        return await self._extract_generic_candidates(page, max_candidates=120)

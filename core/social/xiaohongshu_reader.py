from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

logger = logging.getLogger(__name__)

# =============================================================================
# Xiaohongshu API Client (using signed API)
# =============================================================================

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    from .xiaohongshu_signing import (
        sign_main_api,
        get_common_headers,
        EDITH_HOST,
        USER_AGENT,
    )
    HAS_SIGNING = True
except ImportError:
    HAS_SIGNING = False

# Web-Rooter auth profile integration
try:
    from core.auth_profiles import get_auth_profile_registry
    HAS_AUTH_PROFILES = True
except ImportError:
    HAS_AUTH_PROFILES = False

# Token cache integration
try:
    from .xhs_token_cache import (
        cache_note_context,
        get_cached_note_context,
        invalidate_note_context,
    )
    HAS_TOKEN_CACHE = True
except ImportError:
    HAS_TOKEN_CACHE = False
    

def _get_xiaohongshu_cookies_from_auth_profiles(url: str) -> Dict[str, str]:
    """
    Get xiaohongshu cookies from Web-Rooter's auth profile system.
    
    This function queries the auth profile registry for cookies configured
    for xiaohongshu domains, returning them as a simple name->value dict.
    
    Args:
        url: The target URL (used to match auth profiles)
        
    Returns:
        Dictionary of cookie name -> value
    """
    if not HAS_AUTH_PROFILES:
        return {}
    
    try:
        registry = get_auth_profile_registry()
        payload = registry.collect_auth_payload(url)
        cookies_list = payload.get("cookies", [])
        
        # Convert list of cookie dicts to simple name->value mapping
        cookie_map = {}
        for cookie in cookies_list:
            if isinstance(cookie, dict):
                name = cookie.get("name", "")
                value = cookie.get("value", "")
                if name:
                    cookie_map[name] = value
        
        return cookie_map
    except Exception as exc:
        logger.debug("Failed to get cookies from auth profiles: %s", exc)
        return {}


class XiaohongshuApiClient:
    """
    Xiaohongshu API client using signed requests.
    
    This client uses the xhshow library to generate X-S, X-T, X-S-Common
    headers required to access xiaohongshu's private API (edith.xiaohongshu.com).
    
    Usage:
        >>> cookies = {"a1": "your_a1_value", "web_session": "..."}
        >>> client = XiaohongshuApiClient(cookies)
        >>> note = await client.get_note_by_id("note_id", xsec_token="...")
    """
    
    def __init__(self, cookies: Dict[str, str]):
        if not HAS_HTTPX:
            raise ImportError("httpx is required for XiaohongshuApiClient. Install with: pip install httpx>=0.27.0")
        if not HAS_SIGNING:
            raise ImportError("xhshow signing module is required. Check xiaohongshu_signing.py exists.")
        
        self.cookies = cookies
        self.headers = get_common_headers()
        self.client = httpx.AsyncClient(
            headers=self.headers,
            cookies=cookies,
            timeout=30.0,
            follow_redirects=False,
        )
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def _api_post(self, uri: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Make a signed POST request to the main API."""
        # Generate signed headers
        signed_headers = sign_main_api("POST", uri, self.cookies, payload=payload)
        
        # Merge headers
        headers = {**self.headers, **signed_headers}
        
        # Make request
        url = f"{EDITH_HOST}{uri}"
        response = await self.client.post(url, headers=headers, json=payload)
        
        # Handle common errors
        if response.status_code == 401:
            raise XhsAuthError("Authentication failed - cookie may be expired")
        if response.status_code == 403:
            raise XhsAuthError("Access denied - may need verification (captcha)")
        if response.status_code == 460:
            raise XhsNeedVerifyError("Verification required (anti-bot check)")
        
        response.raise_for_status()
        return response.json()
    
    async def get_note_by_id(
        self, 
        note_id: str, 
        xsec_token: str = "", 
        xsec_source: str = "pc_feed"
    ) -> Dict[str, Any]:
        """
        Get note detail by ID using the feed API.
        
        Args:
            note_id: The note ID (e.g., "67c15b54000000000903c" or 16-char hex)
            xsec_token: Optional xsec_token for authorization
            xsec_source: Source context (default: "pc_feed")
        
        Returns:
            API response JSON as dict
        """
        uri = "/api/sns/web/v1/feed"
        payload = {
            "source_note_id": note_id,
            "xsec_source": xsec_source,
            "xsec_token": xsec_token,
        }
        return await self._api_post(uri, payload)


class XhsApiError(Exception):
    """Base exception for Xiaohongshu API errors."""
    pass


class XhsAuthError(XhsApiError):
    """Authentication failed (401/403)."""
    pass


class XhsNeedVerifyError(XhsApiError):
    """Verification required (460)."""
    pass

_XHS_NOTE_PATH_RE = re.compile(r"/(?:explore|discovery/item)/([a-zA-Z0-9]+)")
_XHS_TOKEN_PATTERNS = [
    re.compile(r'"xsec_token"\s*:\s*"([^"]+)"'),
    re.compile(r"xsec_token=([^&\"']+)"),
    re.compile(r"'xsec_token'\s*:\s*'([^']+)'")
]
_XHS_INITIAL_STATE_RE = re.compile(r"window\.__INITIAL_STATE__\s*=\s*({.*?})\s*</script>", re.DOTALL)
_XHS_CAPTURED_ENDPOINT_RE = re.compile(r"/api/sns/web/(?:v1/feed|v2/comment/page|v2/comment/sub/page)")
_XHS_HOME = "https://www.xiaohongshu.com"

_CAPTURE_INIT_SCRIPT = r"""
(() => {
  if (window.__WR_CAPTURED_JSON__) {
    return;
  }
  const MAX_RECORDS = 64;
  const MAX_TEXT = 350000;
  const records = [];
  const shouldCapture = (url) => {
    if (!url || typeof url !== 'string') return false;
    return /\/api\/sns\/web\/(v1\/feed|v2\/comment\/page|v2\/comment\/sub\/page)/.test(url);
  };
  const pushRecord = (kind, url, status, text) => {
    try {
      if (!shouldCapture(url)) return;
      const payload = typeof text === 'string' ? text.slice(0, MAX_TEXT) : '';
      records.push({ kind, url, status: Number(status || 0), text: payload, ts: Date.now() });
      if (records.length > MAX_RECORDS) {
        records.splice(0, records.length - MAX_RECORDS);
      }
      window.__WR_CAPTURED_JSON__ = records;
    } catch (err) {}
  };
  window.__WR_CAPTURED_JSON__ = records;

  const origFetch = window.fetch;
  if (typeof origFetch === 'function') {
    window.fetch = async (...args) => {
      const resp = await origFetch(...args);
      try {
        const url = resp && resp.url ? resp.url : (args[0] && typeof args[0] === 'string' ? args[0] : '');
        if (shouldCapture(url) && resp && typeof resp.clone === 'function') {
          resp.clone().text().then((text) => pushRecord('fetch', url, resp.status, text)).catch(() => {});
        }
      } catch (err) {}
      return resp;
    };
  }

  const origOpen = XMLHttpRequest.prototype.open;
  const origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    try {
      this.__wr_url__ = typeof url === 'string' ? url : '';
    } catch (err) {}
    return origOpen.call(this, method, url, ...rest);
  };
  XMLHttpRequest.prototype.send = function(body) {
    try {
      this.addEventListener('load', () => {
        try {
          pushRecord('xhr', this.__wr_url__ || this.responseURL || '', this.status || 0, this.responseText || '');
        } catch (err) {}
      });
    } catch (err) {}
    return origSend.call(this, body);
  };
})();
"""


def is_xiaohongshu_detail_url(url: str) -> bool:
    text = str(url or "").strip()
    if not text:
        return False
    parsed = urlparse(text)
    host = (parsed.netloc or "").lower()
    if "xiaohongshu.com" not in host:
        return False
    return _XHS_NOTE_PATH_RE.search(parsed.path or "") is not None


def extract_xiaohongshu_note_ref(value: str) -> Dict[str, str]:
    text = str(value or "").strip()
    if not text:
        return {"input": "", "note_id": "", "url": "", "xsec_token": "", "xsec_source": ""}

    note_id = ""
    url = ""
    xsec_token = ""
    xsec_source = ""

    if text.startswith(("http://", "https://")):
        parsed = urlparse(text)
        match = _XHS_NOTE_PATH_RE.search(parsed.path or "")
        if match:
            note_id = match.group(1)
            query = parse_qs(parsed.query or "")
            xsec_token = (query.get("xsec_token") or [""])[0]
            xsec_source = (query.get("xsec_source") or [""])[0]
            url = text
    elif _XHS_NOTE_PATH_RE.search(text):
        path_match = _XHS_NOTE_PATH_RE.search(text)
        if path_match:
            note_id = path_match.group(1)
            url = _build_note_url(note_id)
    elif re.fullmatch(r"[a-zA-Z0-9]{8,}", text):
        note_id = text
        url = _build_note_url(note_id)

    return {
        "input": text,
        "note_id": note_id,
        "url": url,
        "xsec_token": xsec_token,
        "xsec_source": xsec_source,
    }


def _build_note_url(note_id: str, xsec_token: str = "", xsec_source: str = "pc_feed") -> str:
    if not note_id:
        return ""
    base = f"{_XHS_HOME}/explore/{note_id}"
    if not xsec_token:
        return base
    return base + "?" + urlencode({"xsec_token": xsec_token, "xsec_source": xsec_source or "pc_feed"})


def _extract_token_from_html(html: str) -> Tuple[str, str]:
    if not html:
        return "", ""
    token = ""
    for pattern in _XHS_TOKEN_PATTERNS:
        match = pattern.search(html)
        if match:
            token = match.group(1)
            break
    source_match = re.search(r"xsec_source=([^&\"']+)", html)
    return token, (source_match.group(1) if source_match else "")


def _clean_initial_state_json(raw: str) -> str:
    cleaned = re.sub(r":\s*undefined", ':""', raw)
    cleaned = re.sub(r",\s*undefined", ',""', cleaned)
    return cleaned


def parse_initial_state(html: str) -> Dict[str, Any]:
    if not html:
        return {}
    match = _XHS_INITIAL_STATE_RE.search(html)
    if not match:
        return {}
    raw = _clean_initial_state_json(match.group(1))
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.debug("parse __INITIAL_STATE__ failed: %s", exc)
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_note_from_state(state: Dict[str, Any], note_id: str) -> Dict[str, Any]:
    detail_map = (((state.get("note") or {}).get("noteDetailMap") or {}))
    if not isinstance(detail_map, dict) or not detail_map:
        return {}
    entry: Any = detail_map.get(note_id)
    if entry is None:
        entry = next(iter(detail_map.values()), None)
    if isinstance(entry, dict) and isinstance(entry.get("note"), dict):
        return entry["note"]
    if isinstance(entry, dict):
        return entry
    return {}


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = _stringify(value)
        if text:
            return text
    return ""


def _get_nested(data: Any, path: List[str], default: Any = None) -> Any:
    current = data
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if current is not None else default


def _coerce_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def normalize_note_detail(note: Dict[str, Any], *, note_id: str = "", xsec_token: str = "", xsec_source: str = "") -> Dict[str, Any]:
    user = note.get("user") if isinstance(note.get("user"), dict) else {}
    interact = note.get("interact_info") if isinstance(note.get("interact_info"), dict) else {}
    video = note.get("video") if isinstance(note.get("video"), dict) else {}

    image_list = []
    for item in _coerce_list(note.get("image_list")):
        if not isinstance(item, dict):
            continue
        info = item.get("info_list") if isinstance(item.get("info_list"), list) else []
        candidate = ""
        for info_item in info:
            if isinstance(info_item, dict):
                candidate = _first_non_empty(info_item.get("url"), info_item.get("master_url"))
                if candidate:
                    break
        if not candidate:
            candidate = _first_non_empty(item.get("url_default"), item.get("url"))
        if candidate:
            image_list.append(candidate)

    tags: List[str] = []
    for topic in _coerce_list(note.get("tag_list")) + _coerce_list(note.get("topic_list")):
        if isinstance(topic, dict):
            name = _first_non_empty(topic.get("name"), topic.get("topic_name"), topic.get("display_name"))
        else:
            name = _stringify(topic)
        if name and name not in tags:
            tags.append(name)

    final_note_id = _first_non_empty(note_id, note.get("note_id"), note.get("id"))
    resolved_url = _build_note_url(final_note_id, xsec_token=xsec_token, xsec_source=xsec_source or "pc_feed") if final_note_id else ""

    desc = _first_non_empty(note.get("desc"), note.get("content"), note.get("body"), _get_nested(note, ["share_info", "content"]))
    title = _first_non_empty(note.get("title"), _get_nested(note, ["share_info", "title"]))
    if not title and desc:
        title = desc.splitlines()[0][:80]

    return {
        "note_id": final_note_id,
        "title": title,
        "body": desc,
        "author_name": _first_non_empty(user.get("nickname"), user.get("nick_name"), user.get("name")),
        "author_id": _first_non_empty(user.get("user_id"), user.get("userid"), user.get("id")),
        "author_avatar": _first_non_empty(user.get("avatar"), user.get("avatar_url")),
        "liked_count": _first_non_empty(interact.get("liked_count"), note.get("liked_count")),
        "collected_count": _first_non_empty(interact.get("collected_count"), note.get("collected_count")),
        "comment_count": _first_non_empty(interact.get("comment_count"), note.get("comment_count")),
        "share_count": _first_non_empty(interact.get("share_count"), note.get("share_count")),
        "publish_time": _first_non_empty(note.get("time"), note.get("publish_time"), note.get("last_update_time")),
        "ip_location": _first_non_empty(note.get("ip_location"), note.get("ipLocation")),
        "images": image_list,
        "video_url": _first_non_empty(video.get("consumer"), video.get("media"), video.get("master_url"), video.get("url")),
        "tags": tags,
        "url": resolved_url or _build_note_url(final_note_id),
        "xsec_token": xsec_token,
        "xsec_source": xsec_source,
        "raw": note,
    }


def extract_note_detail_from_feed_payload(payload: Dict[str, Any], *, note_id: str = "") -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    candidates = []
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    for item in _coerce_list(data.get("items")):
        if isinstance(item, dict):
            if isinstance(item.get("note_card"), dict):
                candidates.append((item.get("note_card") or {}, _first_non_empty(item.get("xsec_token"), item.get("note_card", {}).get("xsec_token")), _first_non_empty(item.get("xsec_source"))))
            else:
                candidates.append((item, _first_non_empty(item.get("xsec_token")), _first_non_empty(item.get("xsec_source"))))
    if isinstance(data.get("note"), dict):
        candidates.append((data.get("note") or {}, "", ""))
    for note, token, source in candidates:
        current_id = _first_non_empty(note_id, note.get("note_id"), note.get("id"), data.get("note_id"))
        if current_id and note_id and current_id != note_id:
            continue
        normalized = normalize_note_detail(note, note_id=current_id, xsec_token=token, xsec_source=source or "pc_feed")
        if normalized.get("note_id"):
            return normalized
    return {}


def normalize_comment(comment: Dict[str, Any], *, root_id: str = "") -> Dict[str, Any]:
    user = comment.get("user_info") if isinstance(comment.get("user_info"), dict) else comment.get("user") if isinstance(comment.get("user"), dict) else {}
    content_info = comment.get("content_info") if isinstance(comment.get("content_info"), dict) else {}
    sub_comments = comment.get("sub_comments") if isinstance(comment.get("sub_comments"), list) else []

    normalized = {
        "comment_id": _first_non_empty(comment.get("id"), comment.get("comment_id"), content_info.get("comment_id")),
        "root_comment_id": _first_non_empty(root_id, comment.get("root_comment_id"), comment.get("target_comment", {}).get("id") if isinstance(comment.get("target_comment"), dict) else ""),
        "author_name": _first_non_empty(user.get("nickname"), user.get("nick_name"), user.get("name")),
        "author_id": _first_non_empty(user.get("user_id"), user.get("userid"), user.get("id")),
        "content": _first_non_empty(content_info.get("content"), comment.get("content"), comment.get("text"), comment.get("desc")),
        "like_count": _first_non_empty(comment.get("like_count"), comment.get("liked_count")),
        "time": _first_non_empty(comment.get("create_time"), comment.get("time"), comment.get("ip_location")),
        "ip_location": _first_non_empty(comment.get("ip_location")),
        "sub_comment_count": len(sub_comments),
        "raw": comment,
    }
    return normalized


def normalize_comments_from_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    result: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for comment in _coerce_list(data.get("comments")):
        if not isinstance(comment, dict):
            continue
        normalized = normalize_comment(comment)
        comment_id = normalized.get("comment_id") or f"dom-{len(result)}"
        if comment_id in seen:
            continue
        seen.add(comment_id)
        result.append(normalized)
        for sub in _coerce_list(comment.get("sub_comments")):
            if not isinstance(sub, dict):
                continue
            sub_normalized = normalize_comment(sub, root_id=comment_id)
            sub_id = sub_normalized.get("comment_id") or f"sub-{len(result)}"
            if sub_id in seen:
                continue
            seen.add(sub_id)
            result.append(sub_normalized)
    return result


def _parse_captured_records(records: Any) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
    feed_detail: Dict[str, Any] = {}
    comments: List[Dict[str, Any]] = []
    captured_payloads: List[Dict[str, Any]] = []
    for item in records if isinstance(records, list) else []:
        if not isinstance(item, dict):
            continue
        url = _stringify(item.get("url"))
        if not _XHS_CAPTURED_ENDPOINT_RE.search(url):
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        captured_payloads.append({
            "url": url,
            "kind": _stringify(item.get("kind")),
            "status": item.get("status"),
            "payload": payload,
        })
        if "/v1/feed" in url and not feed_detail:
            feed_detail = extract_note_detail_from_feed_payload(payload)
        if "/v2/comment/page" in url or "/v2/comment/sub/page" in url:
            comments.extend(normalize_comments_from_payload(payload))
    return feed_detail, _dedupe_comments(comments), captured_payloads


def _dedupe_comments(comments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        key = _first_non_empty(comment.get("comment_id"), f"{comment.get('author_name')}::{comment.get('content')[:50]}")
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(comment)
    return deduped


def _extract_dom_comments(items: Any) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []
    comments: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        comment = {
            "comment_id": _first_non_empty(item.get("comment_id"), item.get("id")),
            "root_comment_id": _first_non_empty(item.get("root_comment_id")),
            "author_name": _first_non_empty(item.get("author_name"), item.get("author")),
            "author_id": _first_non_empty(item.get("author_id")),
            "content": _first_non_empty(item.get("content"), item.get("text")),
            "like_count": _first_non_empty(item.get("like_count")),
            "time": _first_non_empty(item.get("time")),
            "ip_location": _first_non_empty(item.get("ip_location")),
            "source": "dom",
            "raw": item,
        }
        if comment["content"]:
            comments.append(comment)
    return _dedupe_comments(comments)


def _summarize_note(detail: Dict[str, Any], comments: List[Dict[str, Any]]) -> str:
    title = _first_non_empty(detail.get("title"), "<无标题>")
    body = _stringify(detail.get("body"))
    author = _first_non_empty(detail.get("author_name"), "<未知作者>")
    stats = []
    for label, key in (("赞", "liked_count"), ("评", "comment_count"), ("藏", "collected_count"), ("转", "share_count")):
        value = _stringify(detail.get(key))
        if value:
            stats.append(f"{label}:{value}")
    lines = [f"小红书笔记：{title}", f"作者：{author}"]
    if stats:
        lines.append("互动：" + " / ".join(stats))
    if body:
        lines.append("正文：\n" + body[:1200])
    if comments:
        lines.append("评论摘录：")
        for idx, comment in enumerate(comments[:8], 1):
            author_name = _first_non_empty(comment.get("author_name"), "匿名")
            content = _stringify(comment.get("content"))
            if not content:
                continue
            lines.append(f"{idx}. {author_name}: {content[:200]}")
    return "\n\n".join(lines)


async def _fetch_note_from_html(
    browser_manager: Any,
    target_url: str,
    note_id: str,
    ref: Dict[str, str],
    *,
    max_comments: int = 40,
    scroll_rounds: int = 8,
    wait_ms: int = 1200,
) -> Dict[str, Any]:
    """
    Fetch note details using HTML scraping (browser-based fallback).
    This is the original implementation preserved for fallback.
    """
    page = await browser_manager._context.new_page()
    try:
        await page.add_init_script(_CAPTURE_INIT_SCRIPT)
        auth_profile = {}
        try:
            auth_profile = await browser_manager._apply_auth_profile(page, target_url)
        except Exception as exc:
            logger.debug("apply auth profile failed for xhs note %s: %s", target_url, exc)

        page.set_default_timeout(30000)
        
        # 尝试多种加载策略，处理小红书的反爬跳转
        load_success = False
        for wait_strategy in ["networkidle", "domcontentloaded", None]:
            try:
                if wait_strategy:
                    await page.goto(target_url, wait_until=wait_strategy, timeout=30000)
                else:
                    await page.goto(target_url, timeout=30000)
                load_success = True
                break
            except Exception as exc:
                logger.debug("xhs goto with %s failed: %s", wait_strategy, exc)
                continue
        
        if not load_success:
            # 最后的兜底尝试
            await page.goto(target_url)
        
        # 等待页面稳定（小红书有客户端路由，需要等JS执行完成）
        await page.wait_for_timeout(max(1500, wait_ms))
        
        # 检查URL是否被重定向（反跳转到首页）
        current_url = page.url
        if "/explore/" not in current_url or current_url.rstrip("/").endswith("/explore"):
            logger.warning("xhs redirected to non-note page: %s", current_url)
        
        # 等待页面完全稳定后再获取内容
        for _ in range(3):
            try:
                html = await page.content()
                break
            except Exception as exc:
                logger.debug("xhs page.content() failed, retrying: %s", exc)
                await page.wait_for_timeout(500)
        else:
            html = ""
        title = await page.title()
        token_from_html, source_from_html = _extract_token_from_html(html)
        xsec_token = ref.get("xsec_token") or token_from_html
        xsec_source = ref.get("xsec_source") or source_from_html or "pc_feed"

        initial_state = parse_initial_state(html)
        state_note = normalize_note_detail(
            _extract_note_from_state(initial_state, note_id),
            note_id=note_id,
            xsec_token=xsec_token,
            xsec_source=xsec_source,
        )

        for _ in range(max(1, scroll_rounds)):
            await page.mouse.wheel(0, 1200)
            await page.wait_for_timeout(max(350, wait_ms))

        dom_comments_raw = await page.evaluate(
            r"""
            () => {
              const selectors = [
                '[class*="comment-item"]',
                '[class*="commentItem"]',
                '[class*="comment_item"]',
                '[class*="CommentItem"]',
                '[data-e2e*="comment"]',
                '[class*="comments"] [class*="item"]',
                '[class*="comment"] li'
              ];
              const map = new Map();
              for (const selector of selectors) {
                for (const el of document.querySelectorAll(selector)) {
                  const text = (el.innerText || '').trim();
                  if (!text || text.length < 2) continue;
                  const author = (
                    el.querySelector('[class*="author"]') ||
                    el.querySelector('[class*="user"]') ||
                    el.querySelector('[class*="name"]')
                  );
                  const contentEl = (
                    el.querySelector('[class*="content"]') ||
                    el.querySelector('[class*="text"]') ||
                    el.querySelector('[class*="desc"]')
                  );
                  const timeEl = el.querySelector('[class*="time"]') || el.querySelector('[class*="date"]');
                  const likeEl = el.querySelector('[class*="like"]');
                  const content = (contentEl ? contentEl.innerText : text).trim();
                  if (!content || content.length < 2) continue;
                  const id = el.getAttribute('data-id') || el.getAttribute('id') || `${(author && author.innerText) || ''}::${content.slice(0, 32)}`;
                  map.set(id, {
                    id,
                    author_name: (author ? author.innerText : '').trim(),
                    content,
                    time: (timeEl ? timeEl.innerText : '').trim(),
                    like_count: (likeEl ? likeEl.innerText : '').trim(),
                  });
                }
              }
              return Array.from(map.values()).slice(0, 120);
            }
            """
        )
        captured_records = await page.evaluate("() => window.__WR_CAPTURED_JSON__ || []")
        feed_detail, api_comments, captured_payloads = _parse_captured_records(captured_records)
        dom_comments = _extract_dom_comments(dom_comments_raw)

        detail = feed_detail or state_note
        if detail and not detail.get("xsec_token") and xsec_token:
            detail["xsec_token"] = xsec_token
            detail["xsec_source"] = xsec_source
            detail["url"] = _build_note_url(detail.get("note_id") or note_id, xsec_token=xsec_token, xsec_source=xsec_source)

        comments = _dedupe_comments(api_comments + dom_comments)[: max(1, max_comments)]
        success = bool(detail.get("note_id") or detail.get("title") or detail.get("body") or comments)
        result = {
            "success": success,
            "platform": "xiaohongshu",
            "url": page.url,
            "input_url": target_url,
            "note_id": note_id,
            "xsec_token": xsec_token,
            "xsec_source": xsec_source,
            "title": title,
            "note_detail": detail,
            "comments": comments,
            "comment_count_captured": len(comments),
            "detail_source": "captured_feed" if feed_detail else "initial_state" if state_note else "dom_only",
            "comments_source": "captured_api" if api_comments else "dom" if dom_comments else "none",
            "captured_api_count": len(captured_payloads),
            "captured_endpoints": [item.get("url") for item in captured_payloads[:20]],
            "auth": auth_profile if isinstance(auth_profile, dict) else {},
            "login_wall": bool(getattr(browser_manager, "_detect_login_wall", None) and browser_manager._detect_login_wall(page.url, title, html)),
            "initial_state_found": bool(initial_state),
            "summary": _summarize_note(detail, comments),
        }
        if not success:
            result["error"] = "xhs_note_and_comments_not_extracted"
        return result
    except Exception as exc:
        logger.exception("read_xiaohongshu_note failed: %s", exc)
        return {
            "success": False,
            "platform": "xiaohongshu",
            "url": target_url,
            "note_id": note_id,
            "error": str(exc),
        }
    finally:
        try:
            if not page.is_closed():
                await page.close()
        except Exception:
            pass


async def _try_fetch_note_via_api(
    cookies: Dict[str, str],
    note_id: str,
    xsec_token: str = "",
    xsec_source: str = "pc_feed",
) -> Optional[Dict[str, Any]]:
    """
    Try to fetch note details via signed API.

    Returns:
        Normalized note detail dict if successful, None otherwise.
    """
    if not HAS_SIGNING or not HAS_HTTPX:
        logger.debug("xhshow signing or httpx not available, skipping API fetch")
        return None

    if not cookies.get("a1"):
        logger.debug("'a1' cookie not available, skipping API fetch")
        return None

    try:
        async with XiaohongshuApiClient(cookies) as client:
            response = await client.get_note_by_id(
                note_id,
                xsec_token=xsec_token,
                xsec_source=xsec_source
            )

            # Check if API call was successful
            if not isinstance(response, dict):
                logger.debug("API response is not a dict: %s", type(response))
                return None

            if response.get("code") != 0:
                logger.debug("API returned error code %s: %s",
                           response.get("code"), response.get("msg"))
                return None

            # Extract note detail from feed response
            detail = extract_note_detail_from_feed_payload(response, note_id=note_id)

            if not detail or not detail.get("note_id"):
                logger.debug("API response did not contain valid note detail")
                return None

            logger.info("Successfully fetched note %s via API", note_id)
            return detail

    except XhsNeedVerifyError:
        logger.warning("API requires verification (anti-bot), falling back to HTML")
        return None
    except XhsAuthError as e:
        logger.warning("API auth failed: %s, falling back to HTML", e)
        return None
    except Exception as exc:
        logger.debug("API fetch failed: %s", exc)
        return None


async def _fetch_note_html(
    browser_manager: Any,
    note_id: str,
    xsec_token: str = "",
    xsec_source: str = "pc_feed",
    target_url: str = "",
    cookies: Optional[Dict[str, str]] = None,
) -> str:
    """
    Fetch note HTML page for token extraction.

    Strategy (migrated from xiaohongshu-cli):
    1. Try httpx direct request with signed headers
    2. Fall back to browser if httpx fails

    Args:
        browser_manager: Browser manager instance
        note_id: The note ID
        xsec_token: Optional xsec_token for URL construction
        xsec_source: Optional xsec_source for URL construction
        target_url: Original target URL (used if no token available)
        cookies: Optional cookies for httpx request

    Returns:
        HTML content string
    """
    # Construct URL
    if xsec_token:
        url = _build_note_url(note_id, xsec_token=xsec_token, xsec_source=xsec_source)
    elif target_url:
        url = target_url
    else:
        url = _build_note_url(note_id)

    # Step 1: Try httpx direct request (like xiaohongshu-cli)
    if cookies and cookies.get("a1"):
        try:
            logger.debug("Trying to fetch HTML via httpx for note %s", note_id)
            import httpx
            from .xiaohongshu_signing import (
                sign_main_api,
                get_common_headers,
                HOME_URL,
                USER_AGENT,
            )

            # Build signed headers
            signed_headers = sign_main_api("GET", f"/explore/{note_id}", cookies, params={"xsec_token": xsec_token, "xsec_source": xsec_source} if xsec_token else None)

            headers = {
                **get_common_headers(),
                **signed_headers,
            }

            async with httpx.AsyncClient(
                headers=headers,
                cookies=cookies,
                timeout=30.0,
                follow_redirects=True,
            ) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    html = response.text
                    logger.debug("Fetched HTML via httpx for note %s (length: %d)", note_id, len(html))
                    return html
                else:
                    logger.debug("httpx returned status %d for note %s", response.status_code, note_id)

        except ImportError as e:
            logger.debug("httpx not available: %s", e)
        except Exception as exc:
            logger.debug("httpx fetch failed for note %s: %s", note_id, exc)

    # Step 2: Fall back to browser
    logger.debug("Falling back to browser for note %s", note_id)
    page = None
    html = ""

    try:
        page = await browser_manager._context.new_page()

        # Quick page load without waiting for full render
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        html = await page.content()
        logger.debug("Fetched HTML via browser for note %s (length: %d)", note_id, len(html))

    except Exception as exc:
        logger.debug("Failed to fetch note HTML via browser: %s", exc)
    finally:
        if page and not page.is_closed():
            await page.close()

    return html


def _resolve_xsec_context(
    note_id: str,
    preferred_token: str = "",
    preferred_source: str = "",
    cached_only: bool = False,
) -> Tuple[str, str]:
    """
    Resolve xsec_token and xsec_source from input, cache, or HTML extraction.

    Strategy:
    1. Use explicit token if provided
    2. Check token cache
    3. If cached_only=True, return empty if not in cache
    4. Otherwise, would fetch HTML to extract token (but this requires browser)

    Args:
        note_id: The note ID
        preferred_token: Explicit xsec_token from URL or caller
        preferred_source: Explicit xsec_source from URL or caller
        cached_only: If True, only check cache, don't fetch HTML

    Returns:
        Tuple of (xsec_token, xsec_source)
    """
    # Step 1: Use explicit token if provided
    if preferred_token:
        if HAS_TOKEN_CACHE:
            cache_note_context(note_id, preferred_token, preferred_source)
        return preferred_token, preferred_source

    # Step 2: Check cache
    if HAS_TOKEN_CACHE:
        cached = get_cached_note_context(note_id)
        if cached.get("token"):
            logger.debug("Using cached xsec_token for note %s", note_id)
            return cached["token"], cached.get("source", "")

    # Step 3: If cached_only, return empty
    if cached_only:
        return "", preferred_source or "pc_feed"

    # Step 4: Would fetch HTML here, but that requires async browser access
    # This is handled by the caller (read_xiaohongshu_note) if needed
    return "", preferred_source or "pc_feed"


async def read_xiaohongshu_note(
    browser_manager: Any,
    target: str,
    *,
    max_comments: int = 40,
    scroll_rounds: int = 8,
    wait_ms: int = 1200,
) -> Dict[str, Any]:
    """
    Read xiaohongshu note details.

    Strategy (migrated from xiaohongshu-cli):
    1. Resolve xsec_token from: explicit -> cache -> HTML extraction
    2. Try signed API with resolved token
    3. Fall back to HTML scraping if API fails or no token
    4. Always fetch HTML for comments (API doesn't return them)

    Args:
        browser_manager: Browser manager instance
        target: URL or note ID
        max_comments: Maximum comments to extract
        scroll_rounds: Number of scroll rounds for HTML extraction
        wait_ms: Wait time between operations

    Returns:
        Dict containing note details, comments, and metadata
    """
    ref = extract_xiaohongshu_note_ref(target)
    note_id = ref.get("note_id") or ""
    target_url = ref.get("url") or target

    if not note_id or not target_url:
        return {
            "success": False,
            "platform": "xiaohongshu",
            "error": "invalid_xiaohongshu_note_ref",
            "note_id": note_id,
            "url": target_url,
        }

    # Ensure browser is started
    if not getattr(browser_manager, "_context", None):
        await browser_manager.start("xiaohongshu")

    # Get cookies for API signing from Web-Rooter's auth profile system
    cookies = _get_xiaohongshu_cookies_from_auth_profiles(target_url)
    logger.debug("Got %d cookies from auth profiles for xiaohongshu", len(cookies))

    # Step 1: Resolve xsec_token (from explicit, cache, or HTML extraction)
    # First try explicit token from URL or cache (without fetching HTML)
    xsec_token = ref.get("xsec_token") or ""
    xsec_source = ref.get("xsec_source") or "pc_feed"

    # Use cache if available, but don't fetch HTML yet
    resolved_token, resolved_source = _resolve_xsec_context(
        note_id,
        preferred_token=xsec_token,
        preferred_source=xsec_source,
        cached_only=True  # Don't fetch HTML yet
    )

    if resolved_token:
        logger.info("Resolved xsec_token for note %s from %s",
                   note_id, "URL" if xsec_token else "cache")
    else:
        logger.info("No xsec_token found in URL or cache for note %s", note_id)

    xsec_token = resolved_token
    xsec_source = resolved_source or "pc_feed"

    # Step 2: Try API with resolved token
    api_detail = None
    if cookies.get("a1") and xsec_token:
        logger.info("Trying to fetch note %s via signed API (token from %s)",
                   note_id, "URL" if ref.get("xsec_token") else "cache")
        api_detail = await _try_fetch_note_via_api(
            cookies, note_id, xsec_token=xsec_token, xsec_source=xsec_source
        )
    elif not cookies.get("a1"):
        logger.info("No 'a1' cookie available, skipping API fetch for note %s", note_id)
    elif not xsec_token:
        logger.info("No 'xsec_token' available, skipping API fetch for note %s", note_id)

    # Step 3: If API failed but we have a token, invalidate cache
    original_xsec_token = xsec_token  # Save for HTML fetch
    if api_detail is None and xsec_token and not ref.get("xsec_token"):
        # Token was from cache, might be stale
        logger.info("API failed with cached token, invalidating cache for note %s", note_id)
        if HAS_TOKEN_CACHE:
            invalidate_note_context(note_id)
        # Don't clear xsec_token - we still need it for HTML fetch with valid token

    # Step 4: If no API success, fetch HTML to extract note detail
    html_fetched = False
    html_content = ""
    if not api_detail:
        logger.info("Fetching HTML to extract note detail for note %s", note_id)
        html = await _fetch_note_html(
            browser_manager, note_id, xsec_token=original_xsec_token, xsec_source=xsec_source, target_url=target_url, cookies=cookies
        )
        html_fetched = True
        html_content = html

        if html:
            # Extract token from HTML if we didn't have one
            if not original_xsec_token:
                extracted_token, extracted_source = _extract_token_from_html(html)
                if extracted_token:
                    logger.info("Extracted xsec_token from HTML for note %s", note_id)
                    xsec_token = extracted_token
                    xsec_source = extracted_source or "pc_feed"

                    # Cache the token for future use
                    if HAS_TOKEN_CACHE:
                        cache_note_context(note_id, xsec_token, xsec_source)

                    # Try API again with extracted token
                    if cookies.get("a1"):
                        logger.info("Retrying API with extracted token for note %s", note_id)
                        api_detail = await _try_fetch_note_via_api(
                            cookies, note_id, xsec_token=xsec_token, xsec_source=xsec_source
                        )

            # If API still failed, try to extract note detail from HTML directly
            if not api_detail or not api_detail.get("note_id"):
                logger.info("Extracting note detail from HTML for note %s", note_id)
                try:
                    state = parse_initial_state(html)
                    if state:
                        note_from_html = _extract_note_from_state(state, note_id)
                        if note_from_html and note_from_html.get("title"):
                            api_detail = note_from_html
                            logger.info("Successfully extracted note detail from HTML")
                except Exception as exc:
                    logger.debug("Failed to extract note from HTML: %s", exc)

    # If API succeeded (or HTML extraction succeeded), return result with minimal HTML fetching for comments
    if api_detail and (api_detail.get("note_id") or api_detail.get("noteId")):
        # Note: API doesn't return comments, so we still need HTML for comments
        # But we can skip the note detail extraction from HTML
        logger.info("Note detail fetched for note %s, fetching comments via HTML", note_id)

        # Normalize note detail (handle both note_id and noteId)
        detail = api_detail
        if not detail.get("note_id") and detail.get("noteId"):
            detail["note_id"] = detail["noteId"]
        if not detail.get("title") and detail.get("title"):
            pass  # Already has title
        detail["xsec_token"] = xsec_token
        detail["xsec_source"] = xsec_source
        detail["url"] = _build_note_url(note_id, xsec_token=xsec_token, xsec_source=xsec_source)
        
        # Try to get comments via HTML (lightweight)
        comments: List[Dict[str, Any]] = []
        page_url = target_url
        auth_profile: Dict[str, Any] = {}
        html = ""
        title = ""
        
        try:
            page = await browser_manager._context.new_page()
            try:
                # Apply auth profile
                try:
                    auth_profile = await browser_manager._apply_auth_profile(page, target_url)
                except Exception as exc:
                    logger.debug("apply auth profile failed: %s", exc)
                
                # Quick page load
                await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)
                
                html = await page.content()
                title = await page.title()
                page_url = page.url
                
                # Scroll for comments
                for _ in range(min(3, scroll_rounds)):
                    await page.mouse.wheel(0, 1200)
                    await page.wait_for_timeout(800)
                
                # Extract comments from DOM
                dom_comments_raw = await page.evaluate(
                    r"""
                    () => {
                      const selectors = [
                        '[class*="comment-item"]',
                        '[class*="commentItem"]',
                        '[class*="comment_item"]',
                        '[class*="CommentItem"]',
                        '[data-e2e*="comment"]',
                        '[class*="comments"] [class*="item"]',
                        '[class*="comment"] li'
                      ];
                      const map = new Map();
                      for (const selector of selectors) {
                        for (const el of document.querySelectorAll(selector)) {
                          const text = (el.innerText || '').trim();
                          if (!text || text.length < 2) continue;
                          const author = (
                            el.querySelector('[class*="author"]') ||
                            el.querySelector('[class*="user"]') ||
                            el.querySelector('[class*="name"]')
                          );
                          const contentEl = (
                            el.querySelector('[class*="content"]') ||
                            el.querySelector('[class*="text"]') ||
                            el.querySelector('[class*="desc"]')
                          );
                          const timeEl = el.querySelector('[class*="time"]') || el.querySelector('[class*="date"]');
                          const likeEl = el.querySelector('[class*="like"]');
                          const content = (contentEl ? contentEl.innerText : text).trim();
                          if (!content || content.length < 2) continue;
                          const id = el.getAttribute('data-id') || el.getAttribute('id') || `${(author && author.innerText) || ''}::${content.slice(0, 32)}`;
                          map.set(id, {
                            id,
                            author_name: (author ? author.innerText : '').trim(),
                            content,
                            time: (timeEl ? timeEl.innerText : '').trim(),
                            like_count: (likeEl ? likeEl.innerText : '').trim(),
                          });
                        }
                      }
                      return Array.from(map.values()).slice(0, 120);
                    }
                    """
                )
                comments = _dedupe_comments(_extract_dom_comments(dom_comments_raw))[: max(1, max_comments)]
                
            finally:
                try:
                    if not page.is_closed():
                        await page.close()
                except Exception:
                    pass
        except Exception as exc:
            logger.debug("Failed to fetch comments via HTML: %s", exc)
        
        success = bool(detail.get("note_id") or detail.get("title") or detail.get("body"))
        result = {
            "success": success,
            "platform": "xiaohongshu",
            "url": page_url,
            "input_url": target_url,
            "note_id": note_id,
            "xsec_token": xsec_token,
            "xsec_source": xsec_source,
            "title": title or detail.get("title", ""),
            "note_detail": detail,
            "comments": comments,
            "comment_count_captured": len(comments),
            "detail_source": "api",
            "comments_source": "dom" if comments else "none",
            "captured_api_count": 0,
            "captured_endpoints": [],
            "auth": auth_profile if isinstance(auth_profile, dict) else {},
            "login_wall": bool(getattr(browser_manager, "_detect_login_wall", None) and browser_manager._detect_login_wall(page_url, title, html)),
            "initial_state_found": False,
            "summary": _summarize_note(detail, comments),
        }
        if not success:
            result["error"] = "xhs_note_api_extracted_but_empty"
        return result
    
    # Fall back to full HTML extraction
    logger.info("API fetch failed or unavailable, falling back to HTML extraction for note %s", note_id)
    return await _fetch_note_from_html(
        browser_manager,
        target_url,
        note_id,
        ref,
        max_comments=max_comments,
        scroll_rounds=scroll_rounds,
        wait_ms=wait_ms,
    )

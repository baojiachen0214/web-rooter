from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import aiohttp

logger = logging.getLogger(__name__)

_BILI_BVID_RE = re.compile(r"\bBV[0-9A-Za-z]{10}\b")
_BILI_VIDEO_PATH_RE = re.compile(r"/video/(BV[0-9A-Za-z]{10})")
_BILI_ARTICLE_PATH_RE = re.compile(r"/(?:read/cv\d+|opus/\d+)")
_BILI_INITIAL_STATE_RE = re.compile(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;?\s*</script>", re.DOTALL)
_BILI_CAPTURED_ENDPOINT_RE = re.compile(r"/x/(?:v2/reply|web-interface/view|web-interface/archive/related)")
_BILI_HOME = "https://www.bilibili.com"
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/133.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Origin": _BILI_HOME,
    "Referer": f"{_BILI_HOME}/",
}

_CAPTURE_INIT_SCRIPT = r"""
(() => {
  if (window.__WR_CAPTURED_JSON__) return;
  const MAX_RECORDS = 64;
  const MAX_TEXT = 400000;
  const records = [];
  const shouldCapture = (url) => {
    if (!url || typeof url !== 'string') return false;
    return /\/x\/(v2\/reply|web-interface\/view|web-interface\/archive\/related)/.test(url);
  };
  const pushRecord = (kind, url, status, text) => {
    try {
      if (!shouldCapture(url)) return;
      records.push({ kind, url, status: Number(status || 0), text: String(text || '').slice(0, MAX_TEXT), ts: Date.now() });
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
    try { this.__wr_url__ = typeof url === 'string' ? url : ''; } catch (err) {}
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


def is_bilibili_video_url(url: str) -> bool:
    text = str(url or "").strip()
    if not text:
        return False
    parsed = urlparse(text)
    host = (parsed.netloc or "").lower()
    if host.endswith("b23.tv"):
        return True
    if "bilibili.com" not in host:
        return False
    return _BILI_VIDEO_PATH_RE.search(parsed.path or "") is not None


def is_bilibili_detail_url(url: str) -> bool:
    text = str(url or "").strip()
    if not text:
        return False
    parsed = urlparse(text)
    host = (parsed.netloc or "").lower()
    if host.endswith("b23.tv"):
        return True
    if "bilibili.com" not in host:
        return False
    path = parsed.path or ""
    return _BILI_VIDEO_PATH_RE.search(path) is not None or _BILI_ARTICLE_PATH_RE.search(path) is not None


def extract_bilibili_video_ref(value: str) -> Dict[str, str]:
    text = str(value or "").strip()
    if not text:
        return {"input": "", "bvid": "", "url": ""}
    bvid = ""
    url = ""
    if text.startswith(("http://", "https://")):
        url = text
        match = _BILI_BVID_RE.search(text)
        if match:
            bvid = match.group(0)
    else:
        match = _BILI_BVID_RE.search(text)
        if match:
            bvid = match.group(0)
            url = f"{_BILI_HOME}/video/{bvid}"
    return {"input": text, "bvid": bvid, "url": url}


def parse_bilibili_initial_state(html: str) -> Dict[str, Any]:
    if not html:
        return {}
    match = _BILI_INITIAL_STATE_RE.search(html)
    if not match:
        return {}
    raw = match.group(1)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.debug("parse bilibili __INITIAL_STATE__ failed: %s", exc)
        return {}
    return parsed if isinstance(parsed, dict) else {}


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


def _coerce_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def normalize_bilibili_video_detail(data: Dict[str, Any], *, bvid: str = "") -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    owner = data.get("owner") if isinstance(data.get("owner"), dict) else {}
    stat = data.get("stat") if isinstance(data.get("stat"), dict) else {}
    pages = data.get("pages") if isinstance(data.get("pages"), list) else []
    cover = _first_non_empty(data.get("pic"), data.get("cover"))
    tags: List[str] = []
    for key in ("tname", "dynamic"):
        value = _first_non_empty(data.get(key))
        if value and value not in tags:
            tags.append(value)
    resolved_bvid = _first_non_empty(bvid, data.get("bvid"))
    body = _first_non_empty(data.get("desc"), data.get("dynamic"), data.get("title"))
    return {
        "bvid": resolved_bvid,
        "title": _first_non_empty(data.get("title")),
        "body": body,
        "author_name": _first_non_empty(owner.get("name"), owner.get("uname")),
        "author_id": _first_non_empty(owner.get("mid"), owner.get("uid")),
        "author_avatar": _first_non_empty(owner.get("face")),
        "view_count": _first_non_empty(stat.get("view"), data.get("view")),
        "danmaku_count": _first_non_empty(stat.get("danmaku"), data.get("danmaku")),
        "reply_count": _first_non_empty(stat.get("reply"), data.get("reply")),
        "like_count": _first_non_empty(stat.get("like"), data.get("like")),
        "coin_count": _first_non_empty(stat.get("coin"), data.get("coin")),
        "favorite_count": _first_non_empty(stat.get("favorite"), data.get("favorite")),
        "share_count": _first_non_empty(stat.get("share"), data.get("share")),
        "publish_time": _first_non_empty(data.get("pubdate"), data.get("ctime")),
        "duration": _first_non_empty(data.get("duration"), pages[0].get("duration") if pages and isinstance(pages[0], dict) else ""),
        "cover": cover,
        "tags": tags,
        "url": f"{_BILI_HOME}/video/{resolved_bvid}" if resolved_bvid else "",
        "aid": _first_non_empty(data.get("aid")),
        "raw": data,
    }


def extract_video_detail_from_state(state: Dict[str, Any], *, bvid: str = "") -> Dict[str, Any]:
    if not isinstance(state, dict):
        return {}
    candidates: List[Dict[str, Any]] = []
    for key in ("videoData", "videoInfo", "archive"):
        item = state.get(key)
        if isinstance(item, dict):
            candidates.append(item)
    for item in candidates:
        candidate_bvid = _first_non_empty(item.get("bvid"), bvid)
        if bvid and candidate_bvid and candidate_bvid != bvid:
            continue
        normalized = normalize_bilibili_video_detail(item, bvid=candidate_bvid)
        if normalized.get("bvid") or normalized.get("title"):
            return normalized
    return {}


def normalize_bilibili_comment(comment: Dict[str, Any], *, root_id: str = "") -> Dict[str, Any]:
    member = comment.get("member") if isinstance(comment.get("member"), dict) else comment.get("user") if isinstance(comment.get("user"), dict) else {}
    content = comment.get("content") if isinstance(comment.get("content"), dict) else {}
    return {
        "comment_id": _first_non_empty(comment.get("rpid_str"), comment.get("rpid"), comment.get("id")),
        "root_comment_id": _first_non_empty(root_id, comment.get("root_str"), comment.get("root")),
        "author_name": _first_non_empty(member.get("uname"), member.get("name")),
        "author_id": _first_non_empty(member.get("mid"), member.get("uid")),
        "content": _first_non_empty(content.get("message"), comment.get("content"), comment.get("text")),
        "like_count": _first_non_empty(comment.get("like"), comment.get("like_count")),
        "time": _first_non_empty(comment.get("ctime"), comment.get("time")),
        "ip_location": _first_non_empty(comment.get("reply_control", {}).get("location") if isinstance(comment.get("reply_control"), dict) else ""),
        "source": "api",
        "raw": comment,
    }


def normalize_bilibili_comments_from_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    replies = data.get("replies") if isinstance(data.get("replies"), list) else []
    result: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for comment in replies:
        if not isinstance(comment, dict):
            continue
        normalized = normalize_bilibili_comment(comment)
        key = normalized.get("comment_id") or f"root-{len(result)}"
        if key not in seen and normalized.get("content"):
            seen.add(key)
            result.append(normalized)
        for sub in _coerce_list(comment.get("replies")):
            if not isinstance(sub, dict):
                continue
            sub_norm = normalize_bilibili_comment(sub, root_id=key)
            sub_key = sub_norm.get("comment_id") or f"sub-{len(result)}"
            if sub_key not in seen and sub_norm.get("content"):
                seen.add(sub_key)
                result.append(sub_norm)
    return result


def _extract_dom_comments(items: Any) -> List[Dict[str, Any]]:
    comments: List[Dict[str, Any]] = []
    seen: set[str] = set()
    if not isinstance(items, list):
        return comments
    for item in items:
        if not isinstance(item, dict):
            continue
        content = _first_non_empty(item.get("content"), item.get("text"))
        if not content:
            continue
        cid = _first_non_empty(item.get("comment_id"), item.get("id"), f"dom-{len(comments)}")
        if cid in seen:
            continue
        seen.add(cid)
        comments.append(
            {
                "comment_id": cid,
                "root_comment_id": _first_non_empty(item.get("root_comment_id")),
                "author_name": _first_non_empty(item.get("author_name"), item.get("author")),
                "author_id": _first_non_empty(item.get("author_id")),
                "content": content,
                "like_count": _first_non_empty(item.get("like_count")),
                "time": _first_non_empty(item.get("time")),
                "source": "dom",
                "raw": item,
            }
        )
    return comments


def _dedupe_comments(comments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        key = _first_non_empty(comment.get("comment_id"), f"{comment.get('author_name')}::{str(comment.get('content') or '')[:50]}")
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(comment)
    return deduped


def _cookie_header(cookies: List[Dict[str, Any]]) -> str:
    pairs: List[str] = []
    for item in cookies:
        if not isinstance(item, dict):
            continue
        name = _stringify(item.get("name"))
        value = _stringify(item.get("value"))
        if name and value:
            pairs.append(f"{name}={value}")
    return "; ".join(pairs)


async def _request_json(url: str, *, headers: Dict[str, str]) -> Dict[str, Any]:
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            payload = await resp.json(content_type=None)
            return payload if isinstance(payload, dict) else {}


async def fetch_bilibili_video_view(bvid: str, *, cookie_header: str = "") -> Dict[str, Any]:
    if not bvid:
        return {}
    headers = dict(_DEFAULT_HEADERS)
    headers["Referer"] = f"{_BILI_HOME}/video/{bvid}/"
    if cookie_header:
        headers["Cookie"] = cookie_header
    payload = await _request_json(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}", headers=headers)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return normalize_bilibili_video_detail(data, bvid=bvid) if data else {}


async def fetch_bilibili_video_comments(*, aid: str = "", bvid: str = "", page: int = 1, cookie_header: str = "") -> List[Dict[str, Any]]:
    if not aid and not bvid:
        return []
    params = []
    if aid:
        params.append(f"oid={aid}")
    params.append("type=1")
    params.append(f"pn={max(1, int(page))}")
    params.append("ps=20")
    params.append("sort=2")
    query = "&".join(params)
    headers = dict(_DEFAULT_HEADERS)
    headers["Referer"] = f"{_BILI_HOME}/video/{bvid}/" if bvid else _BILI_HOME
    if cookie_header:
        headers["Cookie"] = cookie_header
    payload = await _request_json(f"https://api.bilibili.com/x/v2/reply?{query}", headers=headers)
    return normalize_bilibili_comments_from_payload(payload)


def _parse_captured_records(records: Any) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[str]]:
    detail: Dict[str, Any] = {}
    comments: List[Dict[str, Any]] = []
    endpoints: List[str] = []
    for item in records if isinstance(records, list) else []:
        if not isinstance(item, dict):
            continue
        url = _stringify(item.get("url"))
        if not _BILI_CAPTURED_ENDPOINT_RE.search(url):
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        endpoints.append(url)
        if "/x/web-interface/view" in url and not detail:
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            if data:
                detail = normalize_bilibili_video_detail(data, bvid=_first_non_empty(data.get("bvid")))
        if "/x/v2/reply" in url:
            comments.extend(normalize_bilibili_comments_from_payload(payload))
    return detail, _dedupe_comments(comments), endpoints


def _summarize_video(detail: Dict[str, Any], comments: List[Dict[str, Any]]) -> str:
    title = _first_non_empty(detail.get("title"), "<无标题>")
    author = _first_non_empty(detail.get("author_name"), "<未知作者>")
    lines = [f"Bilibili 视频：{title}", f"UP 主：{author}"]
    stats = []
    for label, key in (("播", "view_count"), ("赞", "like_count"), ("评", "reply_count"), ("弹幕", "danmaku_count")):
        value = _first_non_empty(detail.get(key))
        if value:
            stats.append(f"{label}:{value}")
    if stats:
        lines.append("互动：" + " / ".join(stats))
    body = _first_non_empty(detail.get("body"))
    if body:
        lines.append("简介：\n" + body[:1200])
    if comments:
        lines.append("评论摘录：")
        for idx, comment in enumerate(comments[:8], 1):
            author_name = _first_non_empty(comment.get("author_name"), "匿名")
            content = _first_non_empty(comment.get("content"))
            if content:
                lines.append(f"{idx}. {author_name}: {content[:200]}")
    return "\n\n".join(lines)


async def read_bilibili_detail(
    browser_manager: Any,
    target: str,
    *,
    max_comments: int = 40,
    scroll_rounds: int = 5,
    wait_ms: int = 900,
) -> Dict[str, Any]:
    ref = extract_bilibili_video_ref(target)
    target_url = ref.get("url") or target
    if not target_url:
        return {"success": False, "platform": "bilibili", "error": "invalid_bilibili_target", "url": target}

    if not getattr(browser_manager, "_context", None):
        await browser_manager.start("bilibili")

    page = await browser_manager._context.new_page()
    try:
        await page.add_init_script(_CAPTURE_INIT_SCRIPT)
        auth_profile: Dict[str, Any] = {}
        try:
            auth_profile = await browser_manager._apply_auth_profile(page, target_url)
        except Exception as exc:
            logger.debug("apply auth profile failed for bili detail %s: %s", target_url, exc)

        page.set_default_timeout(20000)
        try:
            await page.goto(target_url, wait_until="domcontentloaded")
        except Exception:
            await page.goto(target_url)
        await page.wait_for_timeout(max(400, wait_ms))

        for _ in range(max(1, scroll_rounds)):
            await page.mouse.wheel(0, 1000)
            await page.wait_for_timeout(max(250, wait_ms))

        resolved_url = page.url
        html = await page.content()
        title = await page.title()
        bvid = _first_non_empty(ref.get("bvid"), (_BILI_BVID_RE.search(resolved_url or "") or [""])[0] if _BILI_BVID_RE.search(resolved_url or "") else "")
        if not bvid:
            match = _BILI_BVID_RE.search(html)
            if match:
                bvid = match.group(0)

        initial_state = parse_bilibili_initial_state(html)
        state_detail = extract_video_detail_from_state(initial_state, bvid=bvid)

        dom_comments_raw = await page.evaluate(
            r"""
            () => {
              const selectors = [
                '.reply-item',
                '.sub-reply-item',
                '[class*="reply-item"]',
                '[class*="comment-item"]',
                '[data-id] [class*="reply-content"]'
              ];
              const map = new Map();
              for (const selector of selectors) {
                for (const el of document.querySelectorAll(selector)) {
                  const text = (el.innerText || '').trim();
                  if (!text || text.length < 2) continue;
                  const author = el.querySelector('[class*="user-name"]') || el.querySelector('[class*="name"]');
                  const contentEl = el.querySelector('[class*="reply-content"]') || el.querySelector('[class*="text"]') || el.querySelector('[class*="content"]');
                  const timeEl = el.querySelector('[class*="reply-time"]') || el.querySelector('[class*="time"]');
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
        captured_detail, api_comments, captured_endpoints = _parse_captured_records(captured_records)
        dom_comments = _extract_dom_comments(dom_comments_raw)

        cookie_header = _cookie_header(await page.context.cookies([_BILI_HOME]))
        direct_detail: Dict[str, Any] = {}
        if bvid and not (captured_detail or state_detail):
            try:
                direct_detail = await fetch_bilibili_video_view(bvid, cookie_header=cookie_header)
            except Exception as exc:
                logger.debug("direct bilibili view fetch failed for %s: %s", bvid, exc)

        detail = captured_detail or state_detail or direct_detail
        aid = _first_non_empty(detail.get("aid"))
        direct_comments: List[Dict[str, Any]] = []
        if bvid and aid and not api_comments:
            try:
                direct_comments = await fetch_bilibili_video_comments(aid=aid, bvid=bvid, cookie_header=cookie_header)
            except Exception as exc:
                logger.debug("direct bilibili comments fetch failed for %s: %s", bvid, exc)

        comments = _dedupe_comments(api_comments + direct_comments + dom_comments)[: max(1, max_comments)]
        success = bool(detail.get("bvid") or detail.get("title") or comments)
        result = {
            "success": success,
            "platform": "bilibili",
            "url": resolved_url,
            "input_url": target_url,
            "bvid": bvid,
            "title": title,
            "video_detail": detail,
            "comments": comments,
            "comment_count_captured": len(comments),
            "detail_source": "captured_view" if captured_detail else "initial_state" if state_detail else "direct_api" if direct_detail else "dom_only",
            "comments_source": "captured_api" if api_comments else "direct_api" if direct_comments else "dom" if dom_comments else "none",
            "captured_endpoints": captured_endpoints[:20],
            "auth": auth_profile if isinstance(auth_profile, dict) else {},
            "login_wall": bool(getattr(browser_manager, "_detect_login_wall", None) and browser_manager._detect_login_wall(page.url, title, html)),
            "initial_state_found": bool(initial_state),
            "summary": _summarize_video(detail, comments),
        }
        if not success:
            result["error"] = "bilibili_detail_not_extracted"
        return result
    except Exception as exc:
        logger.exception("read_bilibili_detail failed: %s", exc)
        return {
            "success": False,
            "platform": "bilibili",
            "url": target_url,
            "bvid": ref.get("bvid") or "",
            "error": str(exc),
        }
    finally:
        try:
            if not page.is_closed():
                await page.close()
        except Exception:
            pass


__all__ = [
    "extract_bilibili_video_ref",
    "extract_video_detail_from_state",
    "fetch_bilibili_video_comments",
    "fetch_bilibili_video_view",
    "is_bilibili_detail_url",
    "is_bilibili_video_url",
    "normalize_bilibili_comments_from_payload",
    "normalize_bilibili_video_detail",
    "parse_bilibili_initial_state",
    "read_bilibili_detail",
]

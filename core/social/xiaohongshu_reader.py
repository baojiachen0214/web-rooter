from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

logger = logging.getLogger(__name__)

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


async def read_xiaohongshu_note(
    browser_manager: Any,
    target: str,
    *,
    max_comments: int = 40,
    scroll_rounds: int = 8,
    wait_ms: int = 1200,
) -> Dict[str, Any]:
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

    if not getattr(browser_manager, "_context", None):
        await browser_manager.start("xiaohongshu")

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

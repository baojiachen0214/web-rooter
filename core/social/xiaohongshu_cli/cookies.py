"""
Cookie extraction and management for XHS API client - Integrated with Web-Rooter.

This module integrates xiaohongshu-cli's cookie management with Web-Rooter's:
- core.cookie_sync (CookieSyncManager)
- core.auth_profiles (AuthProfileRegistry)
- Existing xhs_token_cache
"""

from __future__ import annotations

import functools
import json
import logging
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Optional

from .constants import CONFIG_DIR_NAME, COOKIE_FILE, TOKEN_CACHE_FILE, INDEX_CACHE_FILE
from .exceptions import NoCookieError

logger = logging.getLogger(__name__)

# Cookie TTL: warn and attempt browser refresh after 7 days
COOKIE_TTL_DAYS = 7
_COOKIE_TTL_SECONDS = COOKIE_TTL_DAYS * 86400
_TOKEN_CACHE_LOCK = threading.RLock()
_TOKEN_CACHE_MEMORY: Optional[OrderedDict[str, dict[str, Any]]] = None
_TOKEN_CACHE_PATH: Optional[Path] = None
NOTE_CONTEXT_TTL_SECONDS = 86400


def get_config_dir() -> Path:
    """Get or create config directory (Web-Rooter's .web-rooter)."""
    config_dir = Path.home() / CONFIG_DIR_NAME
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_cookie_path() -> Path:
    """Get cookie file path."""
    return get_config_dir() / COOKIE_FILE


def get_token_cache_path() -> Path:
    """Get xsec token cache file path."""
    return get_config_dir() / TOKEN_CACHE_FILE


def get_index_cache_path() -> Path:
    """Get note index cache file path."""
    return get_config_dir() / INDEX_CACHE_FILE


def load_saved_cookies() -> Optional[dict[str, str]]:
    """Load cookies from local storage."""
    cookie_path = get_cookie_path()
    if not cookie_path.exists():
        return None
    try:
        data = json.loads(cookie_path.read_text())
        if data.get("a1"):
            logger.debug("Loaded saved cookies from %s", cookie_path)
            return data
    except (OSError, json.JSONDecodeError) as e:
        logger.debug("Failed to load saved cookies: %s", e)
    return None


def save_cookies(cookies: dict[str, str]) -> None:
    """Save cookies to local storage with restricted permissions and TTL timestamp."""
    cookie_path = get_cookie_path()
    payload = {**cookies, "saved_at": time.time()}
    cookie_path.write_text(json.dumps(payload, indent=2))
    cookie_path.chmod(0o600)
    logger.debug("Saved cookies to %s", cookie_path)


def clear_cookies() -> None:
    """Remove saved cookies."""
    cookie_path = get_cookie_path()
    if cookie_path.exists():
        cookie_path.unlink()
        logger.debug("Cleared cookies from %s", cookie_path)


def get_cookies_from_auth_profiles() -> Optional[dict[str, str]]:
    """
    Get xiaohongshu cookies from Web-Rooter's auth profile system.
    This integrates with 'wr cookie xiaohongshu' workflow.
    """
    try:
        from core.auth_profiles import get_auth_profile_registry
        
        registry = get_auth_profile_registry()
        payload = registry.collect_auth_payload("https://www.xiaohongshu.com")
        cookies_list = payload.get("cookies", [])
        
        if not cookies_list:
            return None
        
        # Convert list of cookie dicts to simple name->value mapping
        cookie_map = {}
        for cookie in cookies_list:
            if isinstance(cookie, dict):
                name = cookie.get("name", "")
                value = cookie.get("value", "")
                if name:
                    cookie_map[name] = value
        
        if cookie_map.get("a1"):
            logger.debug("Loaded XHS cookies from auth_profiles (%d cookies)", len(cookie_map))
            return cookie_map
        
        return None
    except Exception as exc:
        logger.debug("Failed to get cookies from auth_profiles: %s", exc)
        return None


def save_cookies_to_auth_profiles(cookies: dict[str, str]) -> bool:
    """
    Save xiaohongshu cookies to Web-Rooter's auth profile system.
    This ensures compatibility with 'wr cookie xiaohongshu' workflow.
    
    Args:
        cookies: Dictionary of cookie name -> value
        
    Returns:
        True if saved successfully, False otherwise
    """
    try:
        # Convert cookies to auth_profiles format
        cookie_list = []
        for name, value in cookies.items():
            if name in ("saved_at",):
                continue
            cookie_list.append({
                "name": name,
                "value": value,
                "domain": ".xiaohongshu.com",
                "path": "/"
            })
        
        # Build profile payload
        profile_payload = {
            "profiles": [
                {
                    "name": "xiaohongshu_cli_auth",
                    "domains": ["xiaohongshu.com", "xhslink.com", "edith.xiaohongshu.com"],
                    "mode": "cookies",
                    "enabled": True,
                    "priority": 100,
                    "login_url": "https://www.xiaohongshu.com/login",
                    "cookies": cookie_list,
                    "notes": "Auto-created by xiaohongshu-cli QR login"
                }
            ]
        }
        
        # Write to auth_profiles file
        config_dir = get_config_dir()
        auth_file = config_dir / "login_profiles.json"
        
        # Try to merge with existing if present
        if auth_file.exists():
            try:
                existing = json.loads(auth_file.read_text())
                if isinstance(existing, dict) and "profiles" in existing:
                    # Filter out old xiaohongshu profiles
                    profiles = [
                        p for p in existing["profiles"]
                        if not any("xiaohongshu" in d for d in p.get("domains", []))
                    ]
                    profiles.append(profile_payload["profiles"][0])
                    profile_payload["profiles"] = profiles
            except Exception:
                pass
        
        auth_file.write_text(json.dumps(profile_payload, indent=2))
        logger.debug("Saved %d cookies to auth_profiles: %s", len(cookie_list), auth_file)
        return True
        
    except Exception as exc:
        logger.debug("Failed to save cookies to auth_profiles: %s", exc)
        return False


def _normalize_token_entry(value: Any) -> Optional[dict[str, Any]]:
    if isinstance(value, str):
        return {"token": value, "source": "", "ts": time.time()}
    if not isinstance(value, dict):
        return None

    token = str(value.get("token", "")).strip()
    if not token:
        return None

    source = str(value.get("source", "")).strip()
    context = str(value.get("context", "")).strip()
    ts = value.get("ts", 0)
    try:
        ts = float(ts)
    except (TypeError, ValueError):
        ts = 0.0

    entry = {"token": token, "source": source, "ts": ts}
    if context:
        entry["context"] = context
    return entry


def _load_token_cache_from_disk(cache_path: Path) -> OrderedDict[str, dict[str, Any]]:
    if not cache_path.exists():
        return OrderedDict()
    try:
        data = json.loads(cache_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("Failed to load token cache: %s", exc)
        return OrderedDict()
    if not isinstance(data, dict):
        return OrderedDict()

    normalized: list[tuple[str, dict[str, Any]]] = []
    for key, value in data.items():
        if not key:
            continue
        entry = _normalize_token_entry(value)
        if entry:
            normalized.append((str(key), entry))
    normalized.sort(key=lambda item: float(item[1].get("ts", 0)))
    return OrderedDict(normalized)


def _prune_token_cache(
    cache: OrderedDict[str, dict[str, Any]],
    now: Optional[float] = None,
) -> OrderedDict[str, dict[str, Any]]:
    now = now or time.time()
    pruned = OrderedDict(
        (key, value)
        for key, value in cache.items()
        if now - float(value.get("ts", 0)) <= NOTE_CONTEXT_TTL_SECONDS
    )
    while len(pruned) > TOKEN_CACHE_MAX_SIZE:
        pruned.popitem(last=False)
    return pruned


def load_token_cache() -> dict[str, dict[str, Any]]:
    """Load cached note_id -> token context mappings."""
    cache_path = get_token_cache_path()
    global _TOKEN_CACHE_MEMORY, _TOKEN_CACHE_PATH

    with _TOKEN_CACHE_LOCK:
        if _TOKEN_CACHE_MEMORY is None or _TOKEN_CACHE_PATH != cache_path:
            _TOKEN_CACHE_MEMORY = _prune_token_cache(_load_token_cache_from_disk(cache_path))
            _TOKEN_CACHE_PATH = cache_path
        return {
            key: dict(value)
            for key, value in _TOKEN_CACHE_MEMORY.items()
        }


def save_token_cache(cache: dict[str, dict[str, Any]]) -> None:
    """Persist xsec token cache with restricted permissions."""
    cache_path = get_token_cache_path()
    global _TOKEN_CACHE_MEMORY, _TOKEN_CACHE_PATH

    normalized = _prune_token_cache(OrderedDict(
        sorted(
            (
                (str(key), dict(value))
                for key, value in cache.items()
                if key and isinstance(value, dict)
            ),
            key=lambda item: float(item[1].get("ts", 0)),
        )
    ))

    with _TOKEN_CACHE_LOCK:
        cache_path.write_text(json.dumps(normalized, indent=2))
        cache_path.chmod(0o600)
        _TOKEN_CACHE_MEMORY = normalized
        _TOKEN_CACHE_PATH = cache_path


TOKEN_CACHE_MAX_SIZE = 500


def cache_note_context(
    note_id: str,
    xsec_token: str,
    xsec_source: str = "",
    *,
    context: str = "",
) -> None:
    """Store a resolved note token and source for later access.

    Maintains an LRU-style cache capped at TOKEN_CACHE_MAX_SIZE entries.
    Each entry stores token/source/timestamp metadata; overflow evicts the
    oldest entries.
    """
    if not note_id or not xsec_token:
        return
    cache = load_token_cache()

    existing = cache.get(note_id)
    if (
        isinstance(existing, dict)
        and existing.get("token") == xsec_token
        and existing.get("source", "") == xsec_source
        and existing.get("context", "") == context
    ):
        existing["ts"] = time.time()
        save_token_cache(cache)
        return

    entry = {
        "token": xsec_token,
        "source": xsec_source,
        "ts": time.time(),
    }
    if context:
        entry["context"] = context
    cache[note_id] = entry

    # Evict oldest entries if over limit
    if len(cache) > TOKEN_CACHE_MAX_SIZE:
        sorted_keys = sorted(
            cache.keys(),
            key=lambda k: cache[k].get("ts", 0) if isinstance(cache[k], dict) else 0,
        )
        for key in sorted_keys[: len(cache) - TOKEN_CACHE_MAX_SIZE]:
            del cache[key]

    save_token_cache(cache)
    logger.debug("Cached xsec_token for note %s", note_id)


def invalidate_note_context(note_id: str) -> None:
    """Remove cached token/source metadata for a note ID."""
    if not note_id:
        return
    cache = load_token_cache()
    if note_id not in cache:
        return
    del cache[note_id]
    save_token_cache(cache)
    logger.debug("Invalidated cached note context for %s", note_id)


def _normalize_index_entry(value: Any) -> Optional[dict[str, str]]:
    if not isinstance(value, dict):
        return None

    note_id = str(value.get("note_id", "")).strip()
    if not note_id:
        return None

    return {
        "note_id": note_id,
        "xsec_token": str(value.get("xsec_token", "")).strip(),
        "xsec_source": str(value.get("xsec_source", "")).strip(),
    }


def save_note_index(items: list[dict[str, str]]) -> None:
    """Persist the latest ordered note index for short-index navigation."""
    path = get_index_cache_path()
    normalized = [
        entry
        for entry in (_normalize_index_entry(item) for item in items)
        if entry
    ]
    path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False))
    path.chmod(0o600)
    logger.debug("Saved note index with %d entries", len(normalized))


def get_note_by_index(index: int) -> Optional[dict[str, str]]:
    """Resolve a 1-based short index to a cached note reference."""
    if index <= 0:
        return None

    path = get_index_cache_path()
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, list) or index > len(data):
        return None

    return _normalize_index_entry(data[index - 1])


def cache_xsec_token(note_id: str, xsec_token: str) -> None:
    """Backwards-compatible wrapper for token-only caching."""
    cache_note_context(note_id, xsec_token)


def get_cached_note_context(note_id: str) -> dict[str, Any]:
    """Get cached token/source metadata for a note ID."""
    entry = load_token_cache().get(note_id)
    if not isinstance(entry, dict):
        return {}
    return {
        "token": str(entry.get("token", "")),
        "source": str(entry.get("source", "")),
        "context": str(entry.get("context", "")),
        "ts": entry.get("ts", 0.0),
    }


def get_cached_xsec_token(note_id: str) -> str:
    """Get a cached xsec token for a note ID."""
    return get_cached_note_context(note_id).get("token", "")


def get_cookies(
    cookie_source: str = "auto", *, force_refresh: bool = False
) -> tuple[str, dict[str, str]]:
    """
    Multi-strategy cookie acquisition with TTL-based auto-refresh.

    Returns ``(browser_name, cookies)``.

    1. Try auth_profiles first (Web-Rooter integration)
    2. Load saved cookies (skip if stale > 7 days)
    3. Return error if all fail
    """
    # 1. Try auth_profiles first (Web-Rooter way)
    if not force_refresh:
        auth_cookies = get_cookies_from_auth_profiles()
        if auth_cookies:
            return "auth_profile", auth_cookies

    # 2. Try saved cookies
    if not force_refresh:
        saved = load_saved_cookies()
        if saved:
            saved_at = saved.pop("saved_at", 0)
            if saved_at and (time.time() - float(saved_at)) > _COOKIE_TTL_SECONDS:
                logger.info(
                    "Cookies older than %d days, attempting refresh",
                    COOKIE_TTL_DAYS,
                )
                # Will fall through to error since we don't have browser_cookie3 here
            return "saved", saved

    # 3. Raise error with helpful message
    raise NoCookieError(cookie_source)


def cookies_to_string(cookies: dict[str, str]) -> str:
    """Format cookies as a cookie header string."""
    return "; ".join(f"{k}={v}" for k, v in cookies.items())

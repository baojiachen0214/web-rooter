"""
Xiaohongshu Token Cache Module

Provides LRU-style caching for xsec_token and note context metadata.
Used to avoid repeated HTML fetching for the same note ID.

Based on xiaohongshu-cli implementation.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Cache configuration
TOKEN_CACHE_MAX_SIZE = 500  # Max entries in LRU cache
NOTE_CONTEXT_TTL_SECONDS = 86400  # 24 hours

# Thread safety
_TOKEN_CACHE_LOCK = threading.RLock()
_TOKEN_CACHE_MEMORY: OrderedDict[str, dict[str, Any]] | None = None
_TOKEN_CACHE_PATH: Path | None = None


def _get_cache_dir() -> Path:
    """Get or create cache directory."""
    cache_dir = Path.home() / ".web-rooter"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _get_token_cache_path() -> Path:
    """Get xsec token cache file path."""
    return _get_cache_dir() / "xhs_token_cache.json"


def _normalize_token_entry(value: Any) -> dict[str, Any] | None:
    """Normalize a cache entry to a standard format."""
    if not isinstance(value, dict):
        return None

    note_id = str(value.get("note_id", "")).strip()
    if not note_id:
        return None

    return {
        "note_id": note_id,
        "token": str(value.get("token", "")).strip(),
        "source": str(value.get("source", "")).strip(),
        "context": str(value.get("context", "")).strip(),
        "ts": value.get("ts", 0.0),
    }


def _load_token_cache_from_disk() -> OrderedDict[str, dict[str, Any]]:
    """Load token cache from disk, applying TTL expiration."""
    cache_path = _get_token_cache_path()

    if not cache_path.exists():
        return OrderedDict()

    try:
        data = json.loads(cache_path.read_text())
        if not isinstance(data, dict):
            return OrderedDict()

        current_time = time.time()
        result = OrderedDict()

        for key, value in data.items():
            entry = _normalize_token_entry(value)
            if entry is None:
                continue

            # TTL expiration check
            ts = entry.get("ts", 0.0)
            if current_time - ts > NOTE_CONTEXT_TTL_SECONDS:
                logger.debug("Token for note %s expired (age: %.1f hours)",
                           key, (current_time - ts) / 3600)
                continue

            result[key] = entry

        return result

    except (OSError, json.JSONDecodeError) as e:
        logger.debug("Failed to load token cache: %s", e)
        return OrderedDict()


def _prune_token_cache(cache: OrderedDict[str, dict[str, Any]]) -> None:
    """Remove expired entries and enforce max size limit."""
    current_time = time.time()

    # Remove expired entries
    expired_keys = [
        key for key, entry in cache.items()
        if current_time - entry.get("ts", 0.0) > NOTE_CONTEXT_TTL_SECONDS
    ]

    for key in expired_keys:
        del cache[key]
        logger.debug("Removed expired token for note %s", key)

    # Enforce max size (LRU eviction)
    while len(cache) > TOKEN_CACHE_MAX_SIZE:
        # Remove oldest entry (first item in OrderedDict)
        oldest_key = next(iter(cache))
        del cache[oldest_key]
        logger.debug("Evicted oldest token for note %s (max size: %d)",
                    oldest_key, TOKEN_CACHE_MAX_SIZE)


def _save_token_cache_to_disk(cache: OrderedDict[str, dict[str, Any]]) -> None:
    """Save token cache to disk with restricted permissions."""
    cache_path = _get_token_cache_path()

    # Convert OrderedDict to regular dict for JSON serialization
    data = dict(cache)

    try:
        cache_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        cache_path.chmod(0o600)  # Restrict permissions
        logger.debug("Saved token cache to %s (%d entries)", cache_path, len(cache))
    except OSError as e:
        logger.warning("Failed to save token cache: %s", e)


def load_token_cache() -> OrderedDict[str, dict[str, Any]]:
    """
    Load token cache into memory (thread-safe).

    Returns:
        OrderedDict with note_id as key and token metadata as value.
        Each entry contains: token, source, context, ts (timestamp)
    """
    global _TOKEN_CACHE_MEMORY, _TOKEN_CACHE_PATH

    with _TOKEN_CACHE_LOCK:
        if _TOKEN_CACHE_MEMORY is None:
            _TOKEN_CACHE_MEMORY = _load_token_cache_from_disk()
            _TOKEN_CACHE_PATH = _get_token_cache_path()
            logger.debug("Initialized token cache from %s", _TOKEN_CACHE_PATH)

        return _TOKEN_CACHE_MEMORY


def save_token_cache(cache: OrderedDict[str, dict[str, Any]]) -> None:
    """
    Save token cache to disk (thread-safe).

    Args:
        cache: OrderedDict to persist
    """
    with _TOKEN_CACHE_LOCK:
        _prune_token_cache(cache)
        _save_token_cache_to_disk(cache)

        # Update global reference
        global _TOKEN_CACHE_MEMORY
        _TOKEN_CACHE_MEMORY = cache


def cache_note_context(
    note_id: str,
    xsec_token: str,
    xsec_source: str = "",
    *,
    context: str = "",
) -> None:
    """
    Store a resolved note token and source for later access.

    Maintains an LRU-style cache capped at TOKEN_CACHE_MAX_SIZE entries.
    Each entry stores token/source/timestamp metadata; overflow evicts the
    oldest entries.

    Args:
        note_id: The note ID to cache
        xsec_token: The xsec_token value
        xsec_source: Source of the token ("cache", "html", "url", etc.)
        context: Optional context string
    """
    if not note_id or not xsec_token:
        return

    cache = load_token_cache()

    # Check if entry already exists with same values (just refresh timestamp)
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

    # Create new entry
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
    logger.debug("Cached xsec_token for note %s (source: %s)", note_id, xsec_source or "unknown")


def invalidate_note_context(note_id: str) -> None:
    """
    Remove cached token/source metadata for a note ID.

    Args:
        note_id: The note ID to invalidate
    """
    if not note_id:
        return

    cache = load_token_cache()
    if note_id not in cache:
        return

    del cache[note_id]
    save_token_cache(cache)
    logger.debug("Invalidated cached note context for %s", note_id)


def get_cached_note_context(note_id: str) -> dict[str, Any]:
    """
    Get cached token/source metadata for a note ID.

    Args:
        note_id: The note ID to look up

    Returns:
        Dictionary with keys: token, source, context, ts
        Returns empty dict if not found or expired.
    """
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
    """
    Get a cached xsec token for a note ID.

    Args:
        note_id: The note ID to look up

    Returns:
        The cached xsec_token string, or empty string if not found.
    """
    return get_cached_note_context(note_id).get("token", "")


def clear_token_cache() -> None:
    """Clear all cached tokens."""
    cache = load_token_cache()
    cache.clear()
    save_token_cache(cache)
    logger.debug("Cleared all token cache entries")


def get_cache_stats() -> dict[str, Any]:
    """
    Get cache statistics.

    Returns:
        Dictionary with cache size, oldest entry age, newest entry age
    """
    cache = load_token_cache()

    if not cache:
        return {
            "size": 0,
            "oldest_age_hours": 0,
            "newest_age_hours": 0,
        }

    current_time = time.time()
    ages = [(current_time - entry.get("ts", 0)) / 3600 for entry in cache.values()]

    return {
        "size": len(cache),
        "oldest_age_hours": max(ages) if ages else 0,
        "newest_age_hours": min(ages) if ages else 0,
    }

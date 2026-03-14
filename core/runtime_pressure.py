"""
Adaptive runtime pressure controller.

This module turns low-level runtime signals into bounded execution policies:
- memory pressure (RSS)
- short-window error rate

The resulting policy can be consumed by the research kernel to gracefully
degrade behavior instead of crashing due to memory spikes.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, Optional

from core.memory_optimizer import get_memory_optimizer


_LEVEL_ORDER = {
    "normal": 0,
    "elevated": 1,
    "high": 2,
    "critical": 3,
}


def _max_level(level_a: str, level_b: str) -> str:
    return level_a if _LEVEL_ORDER.get(level_a, 0) >= _LEVEL_ORDER.get(level_b, 0) else level_b


@dataclass(frozen=True)
class RuntimePressurePolicy:
    """Thresholds and adaptive limits."""

    elevated_rss_mb: int = 600
    high_rss_mb: int = 900
    critical_rss_mb: int = 1200

    min_error_samples: int = 8
    error_window_size: int = 40
    elevated_error_rate: float = 0.20
    high_error_rate: float = 0.35
    critical_error_rate: float = 0.50

    normal_fetch_html_max_chars: int = 80_000
    elevated_fetch_html_max_chars: int = 60_000
    high_fetch_html_max_chars: int = 35_000
    critical_fetch_html_max_chars: int = 15_000

    normal_text_max_chars: int = 20_000
    elevated_text_max_chars: int = 14_000
    high_text_max_chars: int = 8_000
    critical_text_max_chars: int = 4_000

    normal_links_max: int = 50
    elevated_links_max: int = 30
    high_links_max: int = 16
    critical_links_max: int = 8

    normal_images_max: int = 20
    elevated_images_max: int = 12
    high_images_max: int = 8
    critical_images_max: int = 4

    normal_metadata_items: int = 40
    elevated_metadata_items: int = 28
    high_metadata_items: int = 20
    critical_metadata_items: int = 12

    normal_metadata_depth: int = 3
    elevated_metadata_depth: int = 3
    high_metadata_depth: int = 2
    critical_metadata_depth: int = 2

    normal_metadata_string_chars: int = 500
    elevated_metadata_string_chars: int = 360
    high_metadata_string_chars: int = 240
    critical_metadata_string_chars: int = 160

    # Browser fallback is expensive; we progressively tighten it.
    allow_browser_fallback_normal: bool = True
    allow_browser_fallback_elevated: bool = True
    allow_browser_fallback_high: bool = True
    allow_browser_fallback_critical: bool = False


class RuntimePressureController:
    """Evaluate pressure level and provide adaptive runtime limits."""

    def __init__(self, policy: Optional[RuntimePressurePolicy] = None):
        self._policy = policy or RuntimePressurePolicy()
        self._recent_outcomes: Deque[int] = deque(maxlen=self._policy.error_window_size)
        self._level = "normal"
        self._last_snapshot: Dict[str, Any] = self._build_snapshot(
            level=self._level,
            changed=False,
            previous_level=self._level,
            memory_usage=self._safe_memory_usage(),
            reason="init",
        )

    @property
    def policy(self) -> RuntimePressurePolicy:
        return self._policy

    def clear(self) -> None:
        self._recent_outcomes.clear()
        self._level = "normal"
        self._last_snapshot = self._build_snapshot(
            level=self._level,
            changed=False,
            previous_level=self._level,
            memory_usage=self._safe_memory_usage(),
            reason="reset",
        )

    def record_outcome(self, success: bool) -> None:
        self._recent_outcomes.append(1 if success else 0)

    def evaluate(self, memory_usage: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        usage = memory_usage or self._safe_memory_usage()
        previous = self._level
        memory_level = self._resolve_memory_level(usage)
        error_level = self._resolve_error_level()
        level = _max_level(memory_level, error_level)
        changed = level != previous
        self._level = level

        reason_parts = [f"memory={memory_level}", f"errors={error_level}"]
        if changed:
            reason_parts.append(f"transition={previous}->{level}")
        snapshot = self._build_snapshot(
            level=level,
            changed=changed,
            previous_level=previous,
            memory_usage=usage,
            reason=", ".join(reason_parts),
        )
        self._last_snapshot = snapshot
        return snapshot

    def snapshot(self) -> Dict[str, Any]:
        return dict(self._last_snapshot)

    def get_current_limits(self) -> Dict[str, Any]:
        return self._limits_for_level(self._level)

    def _safe_memory_usage(self) -> Dict[str, Any]:
        try:
            return get_memory_optimizer().check_memory_usage()
        except Exception:
            return {
                "rss_mb": 0.0,
                "vms_mb": 0.0,
                "percent": 0.0,
                "tracked_caches": 0,
                "temp_results": 0,
                "psutil_available": False,
            }

    def _resolve_memory_level(self, usage: Dict[str, Any]) -> str:
        rss_mb = self._safe_float(usage.get("rss_mb"), default=0.0)
        if rss_mb >= self._policy.critical_rss_mb:
            return "critical"
        if rss_mb >= self._policy.high_rss_mb:
            return "high"
        if rss_mb >= self._policy.elevated_rss_mb:
            return "elevated"
        return "normal"

    def _resolve_error_level(self) -> str:
        total = len(self._recent_outcomes)
        if total < self._policy.min_error_samples:
            return "normal"
        failures = total - sum(self._recent_outcomes)
        error_rate = failures / max(1, total)
        if error_rate >= self._policy.critical_error_rate:
            return "critical"
        if error_rate >= self._policy.high_error_rate:
            return "high"
        if error_rate >= self._policy.elevated_error_rate:
            return "elevated"
        return "normal"

    def _build_snapshot(
        self,
        *,
        level: str,
        changed: bool,
        previous_level: str,
        memory_usage: Dict[str, Any],
        reason: str,
    ) -> Dict[str, Any]:
        total = len(self._recent_outcomes)
        failures = total - sum(self._recent_outcomes)
        error_rate = (failures / total) if total > 0 else 0.0
        return {
            "level": level,
            "previous_level": previous_level,
            "changed": changed,
            "reason": reason,
            "memory": memory_usage,
            "errors": {
                "window_size": self._policy.error_window_size,
                "samples": total,
                "failures": failures,
                "error_rate": round(error_rate, 4),
                "min_samples": self._policy.min_error_samples,
            },
            "limits": self._limits_for_level(level),
        }

    def _limits_for_level(self, level: str) -> Dict[str, Any]:
        if level == "critical":
            return {
                "fetch_html_max_chars": self._policy.critical_fetch_html_max_chars,
                "text_max_chars": self._policy.critical_text_max_chars,
                "links_max": self._policy.critical_links_max,
                "images_max": self._policy.critical_images_max,
                "metadata_items": self._policy.critical_metadata_items,
                "metadata_depth": self._policy.critical_metadata_depth,
                "metadata_string_chars": self._policy.critical_metadata_string_chars,
                "allow_browser_fallback": self._policy.allow_browser_fallback_critical,
            }
        if level == "high":
            return {
                "fetch_html_max_chars": self._policy.high_fetch_html_max_chars,
                "text_max_chars": self._policy.high_text_max_chars,
                "links_max": self._policy.high_links_max,
                "images_max": self._policy.high_images_max,
                "metadata_items": self._policy.high_metadata_items,
                "metadata_depth": self._policy.high_metadata_depth,
                "metadata_string_chars": self._policy.high_metadata_string_chars,
                "allow_browser_fallback": self._policy.allow_browser_fallback_high,
            }
        if level == "elevated":
            return {
                "fetch_html_max_chars": self._policy.elevated_fetch_html_max_chars,
                "text_max_chars": self._policy.elevated_text_max_chars,
                "links_max": self._policy.elevated_links_max,
                "images_max": self._policy.elevated_images_max,
                "metadata_items": self._policy.elevated_metadata_items,
                "metadata_depth": self._policy.elevated_metadata_depth,
                "metadata_string_chars": self._policy.elevated_metadata_string_chars,
                "allow_browser_fallback": self._policy.allow_browser_fallback_elevated,
            }
        return {
            "fetch_html_max_chars": self._policy.normal_fetch_html_max_chars,
            "text_max_chars": self._policy.normal_text_max_chars,
            "links_max": self._policy.normal_links_max,
            "images_max": self._policy.normal_images_max,
            "metadata_items": self._policy.normal_metadata_items,
            "metadata_depth": self._policy.normal_metadata_depth,
            "metadata_string_chars": self._policy.normal_metadata_string_chars,
            "allow_browser_fallback": self._policy.allow_browser_fallback_normal,
        }

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

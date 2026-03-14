"""
登录态配置注册与注入。

目标：
- 为需登录平台提供可配置的本地 JSON 模板
- 支持 cookies / storage_state / headers / localStorage 注入
- 让 CLI/MCP 可以给出明确的登录引导
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from core.cli_entry import build_cli_command

logger = logging.getLogger(__name__)

_VALID_MODES = {"manual", "cookies", "headers", "storage_state", "auto"}
_VALID_SAMESITE = {"Lax", "Strict", "None"}


@dataclass
class AuthProfile:
    name: str
    domains: List[str] = field(default_factory=list)
    mode: str = "manual"
    enabled: bool = True
    priority: int = 100
    login_url: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    cookies: List[Dict[str, Any]] = field(default_factory=list)
    cookies_file: Optional[str] = None
    storage_state_file: Optional[str] = None
    local_storage: Dict[str, Dict[str, str]] = field(default_factory=dict)
    notes: str = ""
    source_path: Optional[Path] = None

    def matches_host(self, host: str) -> bool:
        if not host:
            return False
        normalized = host.lower()
        for domain in self.domains:
            token = str(domain or "").strip().lower()
            if not token:
                continue
            if normalized == token or normalized.endswith("." + token):
                return True
        return False

    def match_score(self, host: str) -> int:
        if not self.matches_host(host):
            return -1
        longest = max((len(d) for d in self.domains), default=0)
        return int(self.priority) * 1000 + longest

    @property
    def source(self) -> str:
        if self.source_path is None:
            return "runtime"
        return str(self.source_path)


class AuthProfileRegistry:
    """登录态 profile 注册中心。"""

    def __init__(self):
        self._profiles: Dict[str, AuthProfile] = {}
        self._loaded_paths: set[Path] = set()
        self._load_if_needed()

    @staticmethod
    def _project_root() -> Path:
        return Path(__file__).resolve().parent.parent

    def _template_path(self) -> Path:
        return self._project_root() / "profiles" / "auth" / "login_profiles.template.json"

    def _discover_config_paths(self) -> List[Path]:
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

        default_files = [
            Path.cwd() / ".web-rooter" / "login_profiles.json",
            Path.home() / ".web-rooter" / "login_profiles.json",
        ]
        for path in default_files:
            add_file(path)

        config_dir_env = os.getenv("WEB_ROOTER_AUTH_PROFILE_DIR", "").strip()
        if config_dir_env:
            for raw_dir in config_dir_env.split(os.pathsep):
                if raw_dir.strip():
                    add_dir(Path(raw_dir.strip()))

        config_file_env = os.getenv("WEB_ROOTER_AUTH_PROFILE_FILE", "").strip()
        if config_file_env:
            for raw_file in config_file_env.split(os.pathsep):
                if raw_file.strip():
                    add_file(Path(raw_file.strip()))

        return file_paths

    @staticmethod
    def _load_json(path: Path) -> Optional[Dict[str, Any]]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except Exception as exc:
            logger.warning("加载 auth profile 失败 %s: %s", path, exc)
        return None

    @staticmethod
    def _normalize_domains(raw_domains: Any) -> List[str]:
        if not isinstance(raw_domains, list):
            return []
        domains: List[str] = []
        for item in raw_domains:
            token = str(item or "").strip().lower()
            if token and token not in domains:
                domains.append(token)
        return domains

    def _parse_profile(self, raw: Dict[str, Any], source_path: Path) -> Optional[AuthProfile]:
        name = str(raw.get("name", "")).strip()
        if not name:
            return None

        mode = str(raw.get("mode", "manual")).strip().lower() or "manual"
        if mode not in _VALID_MODES:
            mode = "manual"

        headers = raw.get("headers") or {}
        if not isinstance(headers, dict):
            headers = {}

        cookies = raw.get("cookies") or []
        if not isinstance(cookies, list):
            cookies = []

        local_storage = raw.get("local_storage") or {}
        if not isinstance(local_storage, dict):
            local_storage = {}

        normalized_local_storage: Dict[str, Dict[str, str]] = {}
        for origin, entries in local_storage.items():
            origin_key = str(origin or "").strip()
            if not origin_key or not isinstance(entries, dict):
                continue
            normalized_local_storage[origin_key] = {
                str(k): str(v)
                for k, v in entries.items()
                if str(k).strip()
            }

        return AuthProfile(
            name=name,
            domains=self._normalize_domains(raw.get("domains")),
            mode=mode,
            enabled=bool(raw.get("enabled", True)),
            priority=int(raw.get("priority", 100) or 100),
            login_url=str(raw.get("login_url", "")).strip() or None,
            headers={str(k): str(v) for k, v in headers.items() if str(k).strip()},
            cookies=[item for item in cookies if isinstance(item, dict)],
            cookies_file=str(raw.get("cookies_file", "")).strip() or None,
            storage_state_file=str(raw.get("storage_state_file", "")).strip() or None,
            local_storage=normalized_local_storage,
            notes=str(raw.get("notes", "")).strip(),
            source_path=source_path,
        )

    def _load_if_needed(self, force: bool = False) -> None:
        for path in self._discover_config_paths():
            if not force and path in self._loaded_paths:
                continue
            payload = self._load_json(path)
            if not payload:
                self._loaded_paths.add(path)
                continue

            raw_profiles = payload.get("profiles", [])
            if not isinstance(raw_profiles, list):
                self._loaded_paths.add(path)
                continue

            loaded = 0
            for raw in raw_profiles:
                if not isinstance(raw, dict):
                    continue
                profile = self._parse_profile(raw, source_path=path)
                if profile is None:
                    continue
                self._profiles[profile.name] = profile
                loaded += 1

            if loaded > 0:
                logger.info("已加载 %d 个 auth profiles: %s", loaded, path)
            self._loaded_paths.add(path)

    @staticmethod
    def _host_from_url(url: str) -> str:
        try:
            parsed = urlparse(url)
            return (parsed.hostname or "").lower()
        except Exception:
            return ""

    def resolve(self, url: str) -> Optional[AuthProfile]:
        self._load_if_needed()
        host = self._host_from_url(url)
        if not host:
            return None

        candidates = [
            profile
            for profile in self._profiles.values()
            if profile.enabled and profile.match_score(host) >= 0
        ]
        if not candidates:
            return None

        candidates.sort(key=lambda item: item.match_score(host), reverse=True)
        return candidates[0]

    @staticmethod
    def _resolve_data_path(raw_path: str, profile: AuthProfile) -> Path:
        path = Path(raw_path).expanduser()
        if path.is_absolute():
            return path
        if profile.source_path is not None:
            return (profile.source_path.parent / path).resolve()
        return (Path.cwd() / path).resolve()

    def _load_cookie_records_from_file(self, path: Path) -> List[Dict[str, Any]]:
        payload = self._load_json(path)
        if not payload:
            return []

        cookies_raw: Any = payload
        if isinstance(payload, dict) and isinstance(payload.get("cookies"), list):
            cookies_raw = payload.get("cookies")

        if not isinstance(cookies_raw, list):
            return []
        return [item for item in cookies_raw if isinstance(item, dict)]

    @staticmethod
    def _sanitize_cookie(cookie: Dict[str, Any], host: str) -> Optional[Dict[str, Any]]:
        name = str(cookie.get("name", "")).strip()
        value = str(cookie.get("value", ""))
        if not name:
            return None

        cleaned: Dict[str, Any] = {
            "name": name,
            "value": value,
            "domain": str(cookie.get("domain") or host).strip() or host,
            "path": str(cookie.get("path") or "/").strip() or "/",
        }

        if "expires" in cookie:
            try:
                cleaned["expires"] = float(cookie.get("expires"))
            except Exception:
                pass

        if "httpOnly" in cookie:
            cleaned["httpOnly"] = bool(cookie.get("httpOnly"))
        if "secure" in cookie:
            cleaned["secure"] = bool(cookie.get("secure"))

        same_site_raw = str(cookie.get("sameSite", "")).strip()
        if same_site_raw:
            normalized = same_site_raw[0].upper() + same_site_raw[1:].lower()
            if normalized in _VALID_SAMESITE:
                cleaned["sameSite"] = normalized

        return cleaned

    def collect_auth_payload(self, url: str) -> Dict[str, Any]:
        profile = self.resolve(url)
        host = self._host_from_url(url)
        if profile is None or not host:
            return {
                "matched": None,
                "configured": False,
                "headers": {},
                "cookies": [],
                "local_storage": {},
                "warnings": [],
                "requires_user_input": False,
            }

        warnings: List[str] = []
        cookies: List[Dict[str, Any]] = []
        headers: Dict[str, str] = dict(profile.headers)
        local_storage = dict(profile.local_storage)

        if profile.cookies:
            cookies.extend(profile.cookies)

        if profile.cookies_file:
            cookies_file = self._resolve_data_path(profile.cookies_file, profile)
            if cookies_file.exists():
                cookies.extend(self._load_cookie_records_from_file(cookies_file))
            else:
                warnings.append(f"cookies_file_not_found:{cookies_file}")

        if profile.storage_state_file:
            state_path = self._resolve_data_path(profile.storage_state_file, profile)
            if state_path.exists():
                cookies.extend(self._load_cookie_records_from_file(state_path))
            else:
                warnings.append(f"storage_state_not_found:{state_path}")

        sanitized_cookies = [
            cleaned
            for cleaned in (self._sanitize_cookie(item, host) for item in cookies)
            if cleaned is not None
        ]

        configured = bool(headers or sanitized_cookies or local_storage)
        requires_user_input = (
            profile.mode == "manual"
            or (profile.mode in {"cookies", "storage_state", "auto"} and not configured)
        )

        return {
            "matched": profile.name,
            "source": profile.source,
            "mode": profile.mode,
            "domains": list(profile.domains),
            "login_url": profile.login_url,
            "notes": profile.notes,
            "configured": configured,
            "headers": headers,
            "cookies": sanitized_cookies,
            "local_storage": local_storage,
            "warnings": warnings,
            "requires_user_input": requires_user_input,
        }

    def describe_profiles(self) -> List[Dict[str, Any]]:
        self._load_if_needed()
        rows: List[Dict[str, Any]] = []
        for profile in sorted(self._profiles.values(), key=lambda item: (item.priority, item.name), reverse=True):
            rows.append(
                {
                    "name": profile.name,
                    "enabled": profile.enabled,
                    "priority": profile.priority,
                    "domains": profile.domains,
                    "mode": profile.mode,
                    "login_url": profile.login_url,
                    "notes": profile.notes,
                    "has_headers": bool(profile.headers),
                    "has_cookies": bool(profile.cookies),
                    "has_local_storage": bool(profile.local_storage),
                    "cookies_file": profile.cookies_file,
                    "storage_state_file": profile.storage_state_file,
                    "source": profile.source,
                }
            )
        return rows

    def build_hint(self, url: str) -> Dict[str, Any]:
        payload = self.collect_auth_payload(url)
        payload.pop("headers", None)
        payload.pop("cookies", None)
        payload.pop("local_storage", None)

        if payload.get("matched") is None:
            host = self._host_from_url(url)
            disabled_matches = [
                profile.name
                for profile in self._profiles.values()
                if not profile.enabled and profile.matches_host(host)
            ]
            if disabled_matches:
                payload["disabled_profiles"] = disabled_matches
                payload["hint"] = (
                    "检测到匹配的 profile 但当前为 disabled。请在本地 JSON 中将其 `enabled` 设为 true，"
                    "并补充 cookies/storage_state。"
                )
            else:
                payload["hint"] = (
                    f"未命中登录 profile。可先执行 `{build_cli_command('auth-template')}` 生成本地模板，"
                    "填好 cookies/storage_state 后再重试。"
                )
        elif payload.get("requires_user_input"):
            payload["hint"] = "当前 profile 仍缺登录态，请先手动登录并填充本地 JSON，再让 AI 继续调用抓取命令。"
        else:
            payload["hint"] = "已命中并具备可用登录态配置。"

        return payload

    def export_template(self, output_path: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
        template_path = self._template_path()
        if not template_path.exists():
            raise FileNotFoundError(f"auth template missing: {template_path}")

        target = Path(output_path).expanduser() if output_path else (Path.cwd() / ".web-rooter" / "login_profiles.json")
        target = target.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists() and not force:
            raise FileExistsError(f"target exists: {target}")

        target.write_text(template_path.read_text(encoding="utf-8"), encoding="utf-8")
        return {
            "success": True,
            "output": str(target),
            "template": str(template_path),
            "force": bool(force),
        }


_registry: Optional[AuthProfileRegistry] = None


def get_auth_profile_registry() -> AuthProfileRegistry:
    global _registry
    if _registry is None:
        _registry = AuthProfileRegistry()
    return _registry

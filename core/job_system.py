"""
Local asynchronous job system for long-running `do` tasks.

Design:
- lightweight JSON metadata + result files in `.web-rooter/jobs`
- detached worker process executes job and updates status
- CLI can submit/list/poll/read results
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _jobs_root() -> Path:
    return _project_root() / ".web-rooter" / "jobs"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _trim_scalar(value: Any, max_chars: int) -> str:
    text = "" if value is None else str(value)
    if len(text) <= max_chars:
        return text
    if max_chars <= 16:
        return text[:max_chars]
    return text[: max_chars - 14].rstrip() + "...[truncated]"


def _trim_value(
    value: Any,
    *,
    max_depth: int,
    max_items: int,
    max_string_chars: int,
    depth: int = 0,
) -> Any:
    if depth >= max_depth:
        return _trim_scalar(value, max_string_chars)
    if isinstance(value, str):
        return _trim_scalar(value, max_string_chars)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [
            _trim_value(
                item,
                max_depth=max_depth,
                max_items=max_items,
                max_string_chars=max_string_chars,
                depth=depth + 1,
            )
            for item in value[:max_items]
        ]
    if isinstance(value, dict):
        compact: Dict[str, Any] = {}
        for idx, (key, item) in enumerate(value.items()):
            if idx >= max_items:
                break
            compact[_trim_scalar(key, 120)] = _trim_value(
                item,
                max_depth=max_depth,
                max_items=max_items,
                max_string_chars=max_string_chars,
                depth=depth + 1,
            )
        return compact
    return _trim_scalar(value, max_string_chars)


def _parse_utc_iso(raw: Any) -> Optional[datetime]:
    text = str(raw or "").strip()
    if not text:
        return None
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_terminal_status(status: Any) -> bool:
    token = str(status or "").strip().lower()
    return token in {"completed", "failed", "cancelled"}


def _pid_is_running(pid: Any) -> bool:
    try:
        numeric_pid = int(pid)
    except (TypeError, ValueError):
        return False
    if numeric_pid <= 0:
        return False
    try:
        os.kill(numeric_pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # 进程存在但无权限探测
        return True
    except OSError:
        return False
    return True


class JobStore:
    def __init__(self, root_dir: Optional[Path] = None):
        self._root_dir = root_dir or _jobs_root()
        self._root_dir.mkdir(parents=True, exist_ok=True)

    def _job_dir(self, job_id: str) -> Path:
        return self._root_dir / str(job_id)

    def _meta_path(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "meta.json"

    def _result_path(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "result.json"

    @staticmethod
    def _result_char_budget() -> int:
        return max(20_000, _safe_int(os.getenv("WEB_ROOTER_JOB_RESULT_MAX_CHARS", "220000"), 220_000))

    @staticmethod
    def _result_read_max_bytes() -> int:
        return max(200_000, _safe_int(os.getenv("WEB_ROOTER_JOB_RESULT_READ_MAX_BYTES", "2500000"), 2_500_000))

    @staticmethod
    def _stale_running_timeout_sec() -> int:
        return max(30, _safe_int(os.getenv("WEB_ROOTER_JOB_STALE_RUNNING_SEC", "180"), 180))

    @staticmethod
    def _auto_keep_recent() -> int:
        return max(20, _safe_int(os.getenv("WEB_ROOTER_JOBS_MAX_COUNT", "160"), 160))

    @staticmethod
    def _auto_max_age_days() -> int:
        return max(1, _safe_int(os.getenv("WEB_ROOTER_JOBS_MAX_AGE_DAYS", "14"), 14))

    def create_do_job(
        self,
        task: str,
        options: Dict[str, Any],
        skill: Optional[str],
        strict: bool,
        source: str = "cli",
    ) -> Dict[str, Any]:
        job_id = uuid.uuid4().hex[:12]
        job_dir = self._job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)

        record = {
            "id": job_id,
            "kind": "do_task",
            "status": "queued",
            "task": str(task or ""),
            "skill": (str(skill).strip() if skill else None),
            "strict": bool(strict),
            "options": dict(options or {}),
            "source": str(source or "cli"),
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
            "started_at": None,
            "finished_at": None,
            "pid": None,
            "error": None,
            "result_path": str(self._result_path(job_id)),
        }
        self._meta_path(job_id).write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._auto_prune_jobs()
        return record

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        meta_path = self._meta_path(job_id)
        if not meta_path.exists():
            return None
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return self._reconcile_job_state(data, persist=True)
        except Exception:
            return None
        return None

    def update_job(self, job_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
        record = self.get_job(job_id)
        if not isinstance(record, dict):
            return None
        for key, value in fields.items():
            record[key] = value
        record["updated_at"] = _utc_now_iso()
        self._meta_path(job_id).write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return record

    def list_jobs(self, limit: int = 20, status: Optional[str] = None) -> List[Dict[str, Any]]:
        limit = max(1, int(limit))
        normalized_status = str(status or "").strip().lower() or None
        candidates: List[tuple[datetime, Dict[str, Any]]] = []
        for job_dir in self._root_dir.glob("*"):
            if not job_dir.is_dir():
                continue
            meta_path = job_dir / "meta.json"
            if not meta_path.exists():
                continue
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            data = self._reconcile_job_state(data, persist=True)
            if normalized_status and str(data.get("status") or "").strip().lower() != normalized_status:
                continue
            ts = (
                _parse_utc_iso(data.get("updated_at"))
                or _parse_utc_iso(data.get("finished_at"))
                or _parse_utc_iso(data.get("created_at"))
                or datetime.fromtimestamp(0, tz=timezone.utc)
            )
            candidates.append((ts, data))

        candidates.sort(key=lambda item: item[0], reverse=True)
        items = [item[1] for item in candidates[:limit]]
        return items

    def write_result(self, job_id: str, payload: Dict[str, Any]) -> Optional[str]:
        normalized_payload: Dict[str, Any] = payload if isinstance(payload, dict) else {"result": payload}
        max_chars = self._result_char_budget()
        rendered = json.dumps(normalized_payload, ensure_ascii=False)
        original_chars = len(rendered)

        if original_chars > max_chars:
            compact = _trim_value(
                normalized_payload,
                max_depth=5,
                max_items=80,
                max_string_chars=1800,
            )
            compact_dict: Dict[str, Any]
            if isinstance(compact, dict):
                compact_dict = compact
            else:
                compact_dict = {
                    "success": normalized_payload.get("success"),
                    "error": normalized_payload.get("error"),
                    "result": compact,
                }
            compact_dict["_job_result_truncated"] = {
                "original_chars": original_chars,
                "max_chars": max_chars,
                "reason": "result_payload_too_large",
            }
            normalized_payload = compact_dict
            rendered = json.dumps(normalized_payload, ensure_ascii=False)

        if len(rendered) > max_chars:
            normalized_payload = {
                "success": normalized_payload.get("success") if isinstance(normalized_payload, dict) else None,
                "error": normalized_payload.get("error") if isinstance(normalized_payload, dict) else None,
                "_job_result_truncated": {
                    "original_chars": original_chars,
                    "max_chars": max_chars,
                    "reason": "payload_still_too_large_after_compaction",
                },
                "preview": _trim_scalar(rendered, min(max_chars // 2, 6000)),
            }

        path = self._result_path(job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(normalized_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(path)

    def read_result(self, job_id: str) -> Optional[Dict[str, Any]]:
        path = self._result_path(job_id)
        if not path.exists():
            return None
        max_bytes = self._result_read_max_bytes()
        try:
            file_size = path.stat().st_size
        except Exception:
            file_size = 0
        if file_size > max_bytes:
            return {
                "success": False,
                "error": "job_result_too_large",
                "file_size_bytes": file_size,
                "read_limit_bytes": max_bytes,
                "path": str(path),
            }
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            return None
        return None

    def cleanup_jobs(
        self,
        *,
        keep_recent: int = 120,
        older_than_days: Optional[int] = None,
        include_running: bool = False,
    ) -> Dict[str, Any]:
        keep_recent = max(0, int(keep_recent))
        age_days = max(0, int(older_than_days)) if isinstance(older_than_days, int) else None
        now = datetime.now(timezone.utc)
        threshold = (now - timedelta(days=age_days)) if age_days is not None else None

        terminal_records: List[tuple[Optional[datetime], Path, Dict[str, Any]]] = []
        removed: List[str] = []
        errors: List[str] = []

        for job_dir in sorted(self._root_dir.glob("*"), key=lambda p: p.name):
            if not job_dir.is_dir():
                continue
            meta_path = job_dir / "meta.json"
            if not meta_path.exists():
                continue
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
            if not isinstance(data, dict):
                data = {}

            data = self._reconcile_job_state(data, persist=True)
            status = str(data.get("status") or "").strip().lower()
            created = _parse_utc_iso(data.get("created_at")) or _parse_utc_iso(data.get("updated_at"))

            can_delete = _is_terminal_status(status) or include_running
            if not can_delete:
                continue
            if threshold is not None and created is not None and created <= threshold:
                try:
                    shutil.rmtree(job_dir)
                    removed.append(job_dir.name)
                except Exception as exc:
                    errors.append(f"{job_dir.name}: {exc}")
                continue
            if _is_terminal_status(status):
                terminal_records.append((created, job_dir, data))

        if keep_recent >= 0 and len(terminal_records) > keep_recent:
            def _sort_key(item: tuple[Optional[datetime], Path, Dict[str, Any]]) -> datetime:
                ts = item[0]
                if ts is None:
                    return datetime.fromtimestamp(0, tz=timezone.utc)
                return ts

            terminal_records.sort(key=_sort_key, reverse=True)
            for _, job_dir, _ in terminal_records[keep_recent:]:
                if job_dir.name in removed:
                    continue
                try:
                    shutil.rmtree(job_dir)
                    removed.append(job_dir.name)
                except Exception as exc:
                    errors.append(f"{job_dir.name}: {exc}")

        return {
            "removed_count": len(removed),
            "removed": removed,
            "errors": errors,
            "keep_recent": keep_recent,
            "older_than_days": age_days,
            "include_running": include_running,
        }

    def _reconcile_job_state(self, record: Dict[str, Any], *, persist: bool) -> Dict[str, Any]:
        job_id = str(record.get("id") or "").strip()
        if not job_id:
            return record

        status = str(record.get("status") or "").strip().lower()
        if _is_terminal_status(status):
            return record

        pid = record.get("pid")
        pid_alive = _pid_is_running(pid) if pid is not None else False
        started_at = _parse_utc_iso(record.get("started_at"))
        updated_at = _parse_utc_iso(record.get("updated_at")) or _parse_utc_iso(record.get("created_at"))
        now = datetime.now(timezone.utc)
        timeout_sec = self._stale_running_timeout_sec()
        has_result = self._result_path(job_id).exists()

        should_finalize = False
        next_status = status
        next_error: Optional[str] = None

        if pid is not None and not pid_alive:
            should_finalize = True
            if has_result:
                payload = self.read_result(job_id)
                if isinstance(payload, dict):
                    if str(payload.get("error") or "").strip() == "job_result_too_large":
                        next_status = "completed"
                        next_error = None
                    elif "success" in payload:
                        success = bool(payload.get("success"))
                        next_status = "completed" if success else "failed"
                        next_error = (None if success else "worker_exited_after_result_write")
                    else:
                        next_status = "completed"
                        next_error = None
                else:
                    next_status = "failed"
                    next_error = "worker_exited_with_unreadable_result"
            else:
                next_status = "failed"
                next_error = "worker_exited_without_result"
        elif status == "running":
            if (pid is None or not pid_alive) and started_at and (now - started_at).total_seconds() > timeout_sec:
                should_finalize = True
                next_status = "failed"
                next_error = f"stale_running_timeout:{timeout_sec}s"
        elif status == "queued":
            if (pid is None or not pid_alive) and updated_at and (now - updated_at).total_seconds() > timeout_sec:
                should_finalize = True
                next_status = "failed"
                next_error = f"stale_queued_timeout:{timeout_sec}s"

        if should_finalize:
            record["status"] = next_status
            record["finished_at"] = record.get("finished_at") or datetime.now(timezone.utc).isoformat()
            if next_error:
                record["error"] = next_error
            record["updated_at"] = _utc_now_iso()
            if persist:
                try:
                    self._meta_path(job_id).write_text(
                        json.dumps(record, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                except Exception:
                    pass
        return record

    def _auto_prune_jobs(self) -> None:
        try:
            self.cleanup_jobs(
                keep_recent=self._auto_keep_recent(),
                older_than_days=self._auto_max_age_days(),
                include_running=False,
            )
        except Exception:
            # 自动清理不应影响主流程
            pass


def spawn_job_worker(
    job_id: str,
    python_executable: Optional[str] = None,
    main_script: Optional[Path] = None,
) -> Dict[str, Any]:
    py = python_executable or sys.executable
    script = main_script or (_project_root() / "main.py")
    cmd = [str(py), str(script), "job-worker", str(job_id)]
    kwargs: Dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "cwd": str(_project_root()),
    }
    if os.name == "nt":
        creationflags = 0
        detached_process = getattr(subprocess, "DETACHED_PROCESS", 0)
        new_group = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        creationflags |= detached_process
        creationflags |= new_group
        kwargs["creationflags"] = creationflags
    else:
        kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd, **kwargs)
    return {
        "pid": proc.pid,
        "cmd": cmd,
    }


_store: Optional[JobStore] = None


def get_job_store() -> JobStore:
    global _store
    if _store is None:
        _store = JobStore()
    return _store

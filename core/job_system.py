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
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _jobs_root() -> Path:
    return _project_root() / ".web-rooter" / "jobs"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        return record

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        meta_path = self._meta_path(job_id)
        if not meta_path.exists():
            return None
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
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
        items: List[Dict[str, Any]] = []
        for job_dir in sorted(self._root_dir.glob("*"), key=lambda p: p.name, reverse=True):
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
            if normalized_status and str(data.get("status") or "").strip().lower() != normalized_status:
                continue
            items.append(data)
            if len(items) >= limit:
                break
        return items

    def write_result(self, job_id: str, payload: Dict[str, Any]) -> Optional[str]:
        path = self._result_path(job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(path)

    def read_result(self, job_id: str) -> Optional[Dict[str, Any]]:
        path = self._result_path(job_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            return None
        return None


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

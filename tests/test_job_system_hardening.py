import json
import os
import tempfile
import unittest
from pathlib import Path

from core.job_system import JobStore


class JobSystemHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_result_chars = os.environ.get("WEB_ROOTER_JOB_RESULT_MAX_CHARS")
        self._old_stale_sec = os.environ.get("WEB_ROOTER_JOB_STALE_RUNNING_SEC")

    def tearDown(self) -> None:
        if self._old_result_chars is None:
            os.environ.pop("WEB_ROOTER_JOB_RESULT_MAX_CHARS", None)
        else:
            os.environ["WEB_ROOTER_JOB_RESULT_MAX_CHARS"] = self._old_result_chars

        if self._old_stale_sec is None:
            os.environ.pop("WEB_ROOTER_JOB_STALE_RUNNING_SEC", None)
        else:
            os.environ["WEB_ROOTER_JOB_STALE_RUNNING_SEC"] = self._old_stale_sec

    def test_running_job_with_dead_pid_is_reconciled_to_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp))
            job = store.create_do_job(
                task="demo",
                options={},
                skill=None,
                strict=False,
                source="test",
            )
            store.update_job(
                job["id"],
                status="running",
                pid=99999999,
                started_at="2026-01-01T00:00:00Z",
            )

            updated = store.get_job(job["id"])
            self.assertIsInstance(updated, dict)
            assert updated is not None
            self.assertEqual(updated.get("status"), "failed")
            self.assertEqual(updated.get("error"), "worker_exited_without_result")

    def test_running_job_with_alive_pid_is_not_marked_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp))
            job = store.create_do_job(
                task="demo",
                options={},
                skill=None,
                strict=False,
                source="test",
            )
            store.update_job(
                job["id"],
                status="running",
                pid=os.getpid(),
                started_at="2026-01-01T00:00:00Z",
            )
            updated = store.get_job(job["id"])
            self.assertIsInstance(updated, dict)
            assert updated is not None
            self.assertEqual(updated.get("status"), "running")
            self.assertIsNone(updated.get("finished_at"))

    def test_write_result_compacts_oversized_payload(self) -> None:
        os.environ["WEB_ROOTER_JOB_RESULT_MAX_CHARS"] = "4000"
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp))
            job = store.create_do_job(
                task="demo",
                options={},
                skill=None,
                strict=False,
                source="test",
            )
            big_payload = {
                "success": True,
                "content": "X" * 20000,
                "data": {"html": "Y" * 25000},
            }
            result_path = store.write_result(job["id"], big_payload)
            self.assertIsNotNone(result_path)
            assert result_path is not None

            data = store.read_result(job["id"])
            self.assertIsInstance(data, dict)
            assert data is not None
            self.assertIn("_job_result_truncated", data)
            self.assertTrue((Path(result_path).stat().st_size) < 12000)

    def test_cleanup_jobs_keeps_newest_terminal_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp))
            created_ids = []
            for idx in range(4):
                job = store.create_do_job(
                    task=f"demo-{idx}",
                    options={},
                    skill=None,
                    strict=False,
                    source="test",
                )
                created_ids.append(job["id"])
                store.update_job(
                    job["id"],
                    status="completed",
                    created_at=f"2026-03-0{idx+1}T00:00:00Z",
                    updated_at=f"2026-03-0{idx+1}T00:00:00Z",
                )
                store.write_result(job["id"], {"success": True, "idx": idx})

            summary = store.cleanup_jobs(keep_recent=2, older_than_days=None, include_running=False)
            self.assertEqual(summary.get("removed_count"), 2)

            remaining_dirs = sorted([p.name for p in Path(tmp).iterdir() if p.is_dir()])
            expected_remaining = sorted(created_ids[-2:])
            self.assertEqual(remaining_dirs, expected_remaining)

            for job_id in remaining_dirs:
                meta = json.loads((Path(tmp) / job_id / "meta.json").read_text(encoding="utf-8"))
                self.assertEqual(meta.get("status"), "completed")

    def test_list_jobs_sorted_by_updated_at_desc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp))
            ids = []
            for idx, day in enumerate(["01", "03", "02"]):
                job = store.create_do_job(
                    task=f"sort-{idx}",
                    options={},
                    skill=None,
                    strict=False,
                    source="test",
                )
                ids.append(job["id"])
                store.update_job(
                    job["id"],
                    status="completed",
                    updated_at=f"2026-03-{day}T00:00:00Z",
                    created_at=f"2026-03-{day}T00:00:00Z",
                )
                meta_path = Path(tmp) / job["id"] / "meta.json"
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                meta["updated_at"] = f"2026-03-{day}T00:00:00Z"
                meta["created_at"] = f"2026-03-{day}T00:00:00Z"
                meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

            items = store.list_jobs(limit=3)
            ordered_ids = [item.get("id") for item in items]
            expected = [ids[1], ids[2], ids[0]]  # day=03, day=02, day=01
            self.assertEqual(ordered_ids, expected)

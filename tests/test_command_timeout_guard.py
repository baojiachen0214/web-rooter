import os
import asyncio
import unittest

from main import WebRooterCLI


class _SlowCommandCLI(WebRooterCLI):
    def __init__(self, delay_sec: float):
        super().__init__()
        self.delay_sec = delay_sec
        self.captured_payload = None

    async def run_command(self, command: str, args: list[str]) -> bool:  # type: ignore[override]
        await asyncio.sleep(self.delay_sec)
        return True

    def _print_result(self, result):  # type: ignore[override]
        self.captured_payload = result


class CommandTimeoutGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self._previous_env = os.environ.get("WEB_ROOTER_COMMAND_TIMEOUT_SEC")

    def tearDown(self) -> None:
        if self._previous_env is None:
            os.environ.pop("WEB_ROOTER_COMMAND_TIMEOUT_SEC", None)
        else:
            os.environ["WEB_ROOTER_COMMAND_TIMEOUT_SEC"] = self._previous_env

    def test_quick_accepts_timeout_alias(self) -> None:
        os.environ["WEB_ROOTER_COMMAND_TIMEOUT_SEC"] = "0"
        args, timeout_sec = WebRooterCLI._extract_command_timeout(
            "quick",
            ["RAG benchmark", "--timeout-sec=42"],
        )
        self.assertEqual(args, ["RAG benchmark"])
        self.assertEqual(timeout_sec, 42)

    def test_do_submit_keeps_timeout_for_job_worker(self) -> None:
        os.environ["WEB_ROOTER_COMMAND_TIMEOUT_SEC"] = "90"
        args, timeout_sec = WebRooterCLI._extract_command_timeout(
            "do-submit",
            ["分析 benchmark", "--timeout-sec=1200"],
        )
        self.assertEqual(args, ["分析 benchmark", "--timeout-sec=1200"])
        self.assertIsNone(timeout_sec)

    def test_timeout_target_uses_env_default_when_not_provided(self) -> None:
        os.environ["WEB_ROOTER_COMMAND_TIMEOUT_SEC"] = "77"
        args, timeout_sec = WebRooterCLI._extract_command_timeout(
            "task",
            ["分析这个主题"],
        )
        self.assertEqual(args, ["分析这个主题"])
        self.assertEqual(timeout_sec, 77)


class CommandTimeoutExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_command_safely_emits_structured_timeout(self) -> None:
        cli = _SlowCommandCLI(delay_sec=1.2)
        should_continue = await cli.run_command_safely(
            "quick",
            ["分析这个主题", "--command-timeout-sec=1"],
        )
        self.assertTrue(should_continue)
        self.assertIsInstance(cli.captured_payload, dict)
        payload = cli.captured_payload
        self.assertEqual(payload.get("success"), False)
        self.assertEqual(payload.get("command"), "quick")
        self.assertEqual(payload.get("timeout_sec"), 1)
        self.assertTrue(str(payload.get("error") or "").startswith("command_timeout:quick"))

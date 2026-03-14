import io
import json
import os
import unittest
from contextlib import redirect_stdout

from main import WebRooterCLI


class CLIOutputFormatTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_max_chars = os.environ.get("WEB_ROOTER_MAX_OUTPUT_CHARS")
        self._old_no_rich = os.environ.get("WEB_ROOTER_NO_RICH")
        os.environ["WEB_ROOTER_MAX_OUTPUT_CHARS"] = "600"
        os.environ["WEB_ROOTER_NO_RICH"] = "1"

    def tearDown(self) -> None:
        if self._old_max_chars is None:
            os.environ.pop("WEB_ROOTER_MAX_OUTPUT_CHARS", None)
        else:
            os.environ["WEB_ROOTER_MAX_OUTPUT_CHARS"] = self._old_max_chars

        if self._old_no_rich is None:
            os.environ.pop("WEB_ROOTER_NO_RICH", None)
        else:
            os.environ["WEB_ROOTER_NO_RICH"] = self._old_no_rich

    def test_truncated_output_remains_valid_json(self) -> None:
        cli = WebRooterCLI()
        payload = {
            "success": True,
            "content": "x" * 5000,
            "data": {
                "html": "y" * 12000,
            },
        }

        stream = io.StringIO()
        with redirect_stdout(stream):
            cli._print_result(payload)

        text = stream.getvalue().strip()
        parsed = json.loads(text)
        self.assertEqual(parsed.get("success"), True)
        self.assertTrue(parsed.get("truncated"))
        self.assertEqual(parsed.get("output_limit_chars"), 600)

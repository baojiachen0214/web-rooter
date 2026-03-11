from __future__ import annotations

from main import WebRooterCLI


def test_unknown_command_typo_payload_has_suggestions() -> None:
    cli = WebRooterCLI()
    payload = cli._build_unknown_command_payload("socal")
    assert isinstance(payload, dict)
    suggestions = payload.get("suggestions")
    assert isinstance(suggestions, list)
    assert "social" in suggestions


def test_unknown_non_command_text_not_blocked() -> None:
    cli = WebRooterCLI()
    payload = cli._build_unknown_command_payload("量化交易")
    assert payload is None

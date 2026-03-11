from __future__ import annotations

from agents.web_agent import WebAgent
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


def test_unknown_command_recovery_builds_skill_guidance() -> None:
    cli = WebRooterCLI()
    cli.agent = WebAgent()
    payload = cli._build_unknown_command_payload(
        "socal",
        args=["抓取知乎评论区观点并给出处"],
    )
    assert isinstance(payload, dict)
    auto_resolution = payload.get("auto_resolution")
    assert isinstance(auto_resolution, dict)
    assert auto_resolution.get("goal") == "抓取知乎评论区观点并给出处"
    assert auto_resolution.get("selected_skill") == "social_comment_mining"
    recommended = payload.get("recommended")
    assert isinstance(recommended, list)
    assert any("--skill=social_comment_mining" in item for item in recommended)

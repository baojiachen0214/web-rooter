from __future__ import annotations

from core.command_ir import build_command_ir, lint_command_ir, summarize_lint, has_lint_errors
from core.workflow import get_workflow_schema
from core.skills import SkillRegistry
from agents.web_agent import WebAgent


def test_lint_command_ir_valid_workflow() -> None:
    spec = {
        "name": "lint-demo",
        "variables": {"query": "agent engineering"},
        "steps": [
            {
                "id": "s1",
                "tool": "search_internet",
                "args": {"query": "${vars.query}", "num_results": 5, "auto_crawl": False},
            }
        ],
    }
    ir = build_command_ir(
        command="do",
        goal="demo goal",
        route="general",
        workflow_spec=spec,
        options={},
        dry_run=True,
    )
    issues = lint_command_ir(ir, workflow_schema=get_workflow_schema())
    assert not has_lint_errors(issues)
    summary = summarize_lint(issues)
    assert summary["valid"] is True
    assert summary["error_count"] == 0


def test_lint_command_ir_unknown_tool_error() -> None:
    spec = {
        "name": "lint-demo",
        "variables": {"query": "agent engineering"},
        "steps": [
            {
                "id": "s1",
                "tool": "unknown_tool_x",
                "args": {"query": "${vars.query}"},
            }
        ],
    }
    ir = build_command_ir(
        command="do",
        goal="demo goal",
        route="general",
        workflow_spec=spec,
        options={},
        dry_run=True,
    )
    issues = lint_command_ir(ir, workflow_schema=get_workflow_schema())
    assert has_lint_errors(issues)
    assert any(item.get("code") == "workflow.unknown_tool" for item in issues if isinstance(item, dict))


def test_skill_registry_resolve_social_route() -> None:
    registry = SkillRegistry()
    profile, resolution = registry.resolve("抓取知乎评论区观点并给出处")
    assert profile is not None
    assert profile.route in {"social", "auto"}
    assert isinstance(profile.phases, list)
    assert isinstance(resolution, dict)
    assert resolution.get("selected")


def test_web_agent_build_skill_playbook() -> None:
    agent = WebAgent()
    payload = agent.build_skill_playbook(
        task="抓取知乎评论区观点并给出处",
        explicit_skill="social_comment_mining",
        strict=False,
    )
    assert payload.get("success") is True
    assert payload.get("selected_skill") == "social_comment_mining"
    commands = payload.get("recommended_cli_sequence")
    assert isinstance(commands, list) and len(commands) >= 3

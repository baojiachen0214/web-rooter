from __future__ import annotations

import asyncio

from core.command_ir import build_command_ir, lint_command_ir, summarize_lint, has_lint_errors
from core.workflow import get_workflow_schema, WorkflowRunner, build_workflow_template
from core.skills import SkillRegistry
from core.search.engine_config import ConfigLoader
from core.search.advanced import AdvancedSearchEngine, _get_engine_search_url_templates
from core.search.engine import MultiSearchEngine, SearchEngine
from core.version import APP_NAME, APP_VERSION, APP_VERSION_TAG
from core import __version__
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


def test_skill_registry_ambiguous_query_falls_back_default() -> None:
    registry = SkillRegistry()
    profile, resolution = registry.resolve("量化交易 因子 最新讨论")
    assert profile is not None
    assert profile.name == "default_general_research"
    assert resolution.get("selected") == "default_general_research"
    assert resolution.get("fallback_reason")


def test_skill_registry_social_activation_selected() -> None:
    registry = SkillRegistry()
    profile, resolution = registry.resolve("抓取知乎评论区对 iPhone 17 的观点并给出处")
    assert profile is not None
    assert profile.name == "social_comment_mining"
    detail = resolution.get("selected_detail")
    assert isinstance(detail, dict)
    hits = detail.get("activation_hits")
    assert isinstance(hits, list) and len(hits) >= 1


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
    phase_wakeup = payload.get("phase_wakeup")
    assert isinstance(phase_wakeup, list) and len(phase_wakeup) >= 2
    assert any(isinstance(item, dict) and item.get("id") == "dry_run" for item in phase_wakeup)
    contract = payload.get("ai_contract")
    assert isinstance(contract, dict)
    assert contract.get("mode") == "phase_serial"


def test_web_agent_build_skill_probe() -> None:
    agent = WebAgent()
    payload = agent.build_skill_probe(
        task="抓取知乎评论区观点并给出处",
        command_name="skills_probe_test",
    )
    assert payload.get("success") is True
    assert payload.get("selected_skill") == "social_comment_mining"
    assert payload.get("route") in {"social", "general"}
    playbook = payload.get("playbook")
    assert isinstance(playbook, dict)
    commands = playbook.get("recommended_cli_sequence")
    assert isinstance(commands, list) and len(commands) >= 3
    confidence = payload.get("confidence")
    assert isinstance(confidence, dict)
    assert isinstance(confidence.get("activation_hits"), list)


def test_quark_engine_config_and_templates() -> None:
    loader = ConfigLoader.get_instance()
    loader.load_configs(force=True)
    cfg = loader.get_engine_config("quark")
    assert cfg is not None
    assert cfg.baseUrl.startswith("https://www.quark.cn")
    assert cfg.searchPath == "/s?q="

    templates = _get_engine_search_url_templates(AdvancedSearchEngine.QUARK)
    assert isinstance(templates, list) and len(templates) >= 1
    assert any("quark" in item for item in templates)
    assert all("{query}" in item for item in templates)


def test_multi_search_engine_prefers_quark_for_chinese_query() -> None:
    engine = MultiSearchEngine()
    selected = engine._select_engines("量化交易 因子")
    assert selected[0] == SearchEngine.QUARK
    assert selected[1] == SearchEngine.BAIDU
    assert SearchEngine.BING in selected


def test_web_agent_search_engine_order_prefers_quark_then_baidu() -> None:
    agent = WebAgent()
    selected = agent._select_search_engines("知乎 评论区 观点")
    assert selected[0] == SearchEngine.BING
    assert selected[1] == SearchEngine.QUARK
    assert selected[2] == SearchEngine.BAIDU


def test_academic_workflow_template_mindsearch_is_optional() -> None:
    spec = build_workflow_template("academic_relations")
    runtime = spec.get("runtime")
    assert isinstance(runtime, dict)
    assert int(runtime.get("budget_sec", 0)) >= 120
    assert int(runtime.get("min_optional_remaining_sec", 0)) >= 20

    step_ids = [item.get("id") for item in spec.get("steps", []) if isinstance(item, dict)]
    assert "visit_top_papers" in step_ids
    assert "mindsearch_relation" in step_ids
    assert step_ids.index("visit_top_papers") < step_ids.index("mindsearch_relation")

    steps = spec.get("steps", [])
    academic_step = next(
        (item for item in steps if isinstance(item, dict) and item.get("id") == "academic_search"),
        None,
    )
    assert isinstance(academic_step, dict)
    assert int(academic_step.get("timeout_sec", 0)) >= 30
    assert int(academic_step.get("degrade_below_sec", 0)) >= 60

    mindsearch_step = next(
        (item for item in steps if isinstance(item, dict) and item.get("id") == "mindsearch_relation"),
        None,
    )
    assert isinstance(mindsearch_step, dict)
    assert mindsearch_step.get("continue_on_error") is True
    assert int(mindsearch_step.get("timeout_sec", 0)) >= 30


def test_workflow_strict_mode_respects_optional_step_failures() -> None:
    runner = WorkflowRunner(agent=object())
    spec = {
        "name": "strict-optional",
        "steps": [
            {"id": "optional_fail", "tool": "unknown_tool", "continue_on_error": True, "args": {}},
            {"id": "echo_ok", "tool": "echo", "args": {"value": "ok"}},
        ],
    }
    payload = asyncio.run(runner.run_spec(spec=spec, strict=True))
    assert payload.get("success") is True
    assert payload.get("failed_step") is None
    assert int(payload.get("soft_failed_steps") or 0) >= 1


def test_workflow_budget_skips_optional_step_when_remaining_low() -> None:
    runner = WorkflowRunner(agent=object())
    spec = {
        "name": "budget-skip-optional",
        "runtime": {
            "budget_sec": 1,
            "min_optional_remaining_sec": 2,
        },
        "steps": [
            {"id": "warmup", "tool": "sleep", "args": {"seconds": 0.05}},
            {"id": "optional_step", "tool": "echo", "continue_on_error": True, "args": {"value": "x"}},
        ],
    }
    payload = asyncio.run(runner.run_spec(spec=spec, strict=True))
    assert payload.get("success") is True
    optional_output = payload.get("steps", {}).get("optional_step", {})
    assert optional_output.get("reason") == "budget_low_skip_optional"
    reports = payload.get("reports", [])
    optional_report = next(
        (item for item in reports if isinstance(item, dict) and item.get("id") == "optional_step"),
        {},
    )
    assert optional_report.get("status") == "soft_failed"


def test_workflow_budget_degrade_args_applied() -> None:
    runner = WorkflowRunner(agent=object())
    spec = {
        "name": "budget-degrade",
        "runtime": {"budget_sec": 10},
        "steps": [
            {
                "id": "degrade_echo",
                "tool": "echo",
                "degrade_below_sec": 20,
                "degrade_args": {"value": "degraded"},
                "args": {"value": "original"},
            }
        ],
    }
    payload = asyncio.run(runner.run_spec(spec=spec, strict=False))
    assert payload.get("success") is True
    output = payload.get("steps", {}).get("degrade_echo", {})
    assert output.get("value") == "degraded"
    report = next(
        (item for item in payload.get("reports", []) if isinstance(item, dict) and item.get("id") == "degrade_echo"),
        {},
    )
    metadata = report.get("metadata", {})
    assert isinstance(metadata, dict)
    assert metadata.get("degraded") is True


def test_workflow_early_stop_after_soft_failed_threshold() -> None:
    runner = WorkflowRunner(agent=object())
    spec = {
        "name": "early-stop-soft-failed",
        "runtime": {"early_stop_soft_failed_steps": 1},
        "steps": [
            {"id": "optional_fail_1", "tool": "unknown_tool", "continue_on_error": True, "args": {}},
            {"id": "optional_fail_2", "tool": "unknown_tool", "continue_on_error": True, "args": {}},
            {"id": "echo_tail", "tool": "echo", "args": {"value": "tail"}},
        ],
    }
    payload = asyncio.run(runner.run_spec(spec=spec, strict=False))
    assert payload.get("success") is True
    assert payload.get("early_stop_reason") == "soft_failed_threshold:1"
    assert "optional_fail_1" in payload.get("steps", {})
    assert "optional_fail_2" not in payload.get("steps", {})
    assert "echo_tail" not in payload.get("steps", {})


def test_workflow_for_each_item_timeout_is_captured() -> None:
    runner = WorkflowRunner(agent=object())
    spec = {
        "name": "item-timeout-loop",
        "variables": {"nums": [1, 2]},
        "steps": [
            {
                "id": "loop_sleep",
                "tool": "sleep",
                "for_each": "${vars.nums}",
                "item_alias": "n",
                "max_items": 2,
                "item_timeout_sec": 1,
                "continue_on_error": True,
                "args": {"seconds": 2},
            }
        ],
    }
    payload = asyncio.run(runner.run_spec(spec=spec, strict=True))
    assert payload.get("success") is True
    step_out = payload.get("steps", {}).get("loop_sleep", {})
    assert isinstance(step_out, dict)
    assert int(step_out.get("failed_count") or 0) >= 1
    items = step_out.get("items", [])
    assert isinstance(items, list) and len(items) >= 1
    assert any(
        isinstance(item, dict) and str(item.get("error") or "").startswith("item_timeout:")
        for item in items
    )


def test_version_single_source_of_truth() -> None:
    assert __version__ == APP_VERSION
    assert APP_NAME == "web-rooter"
    assert APP_VERSION_TAG == f"v{APP_VERSION}"


def test_version_is_pre_1_semver() -> None:
    parts = APP_VERSION.split(".")
    assert len(parts) == 3
    major, minor, patch = (int(parts[0]), int(parts[1]), int(parts[2]))
    assert major == 0
    assert minor >= 0
    assert patch >= 0

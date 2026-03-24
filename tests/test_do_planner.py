from agents.web_agent import WebAgent
from core.do_planner import PlannerOptions, get_do_planner_registry


def test_do_planner_selects_xiaohongshu_detail_strategy() -> None:
    registry = get_do_planner_registry()
    spec = registry.analyze_task(
        "读取这个小红书帖子正文和评论区 https://www.xiaohongshu.com/explore/abc123?xsec_token=tok"
    )
    assert spec.route_family == "social"
    assert spec.target_kind == "social_detail"
    assert spec.platform == "xiaohongshu"
    assert spec.comment_intent is True
    decision = registry.plan(spec, PlannerOptions(html_first=True, top_results=5, use_browser=False))
    assert decision.strategy_name == "xiaohongshu_detail"
    assert decision.route == "social"
    assert decision.workflow_spec["name"] == "direct-social-detail-analysis"
    assert decision.workflow_spec["variables"]["platform"] == "xiaohongshu"
    assert decision.completion_contract.get("fallback_chain")


def test_compile_task_ir_exposes_task_spec_and_planning() -> None:
    agent = WebAgent()
    payload = agent.compile_task_ir(
        task="读取这个小红书帖子正文和评论区 https://www.xiaohongshu.com/explore/abc123?xsec_token=tok",
        dry_run=True,
    )
    assert payload.get("success") is True
    task_spec = payload.get("task_spec")
    planning = payload.get("planning")
    assert isinstance(task_spec, dict)
    assert task_spec.get("platform") == "xiaohongshu"
    assert task_spec.get("target_kind") == "social_detail"
    assert isinstance(planning, dict)
    assert planning.get("strategy_name") == "xiaohongshu_detail"
    assert planning.get("completion_contract")
    ir = payload.get("ir")
    assert isinstance(ir, dict)
    assert ir.get("metadata", {}).get("strategy_name") == "xiaohongshu_detail"


def test_do_planner_selects_bilibili_detail_strategy() -> None:
    registry = get_do_planner_registry()
    spec = registry.analyze_task(
        "读取这个 Bilibili 视频正文和评论区 https://www.bilibili.com/video/BV1xx411c7mD/"
    )
    assert spec.route_family == "social"
    assert spec.target_kind == "social_detail"
    assert spec.platform == "bilibili"
    decision = registry.plan(spec, PlannerOptions(html_first=True, top_results=5, use_browser=False))
    assert decision.strategy_name == "bilibili_detail"
    assert decision.workflow_spec["variables"]["platform"] == "bilibili"
    assert decision.completion_contract.get("fallback_chain")

from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

from core.micro_skills import build_micro_skill_hints

if TYPE_CHECKING:
    from agents.web_agent import AgentResponse, WebAgent


def build_skill_playbook_payload(
    agent: "WebAgent",
    task: str,
    explicit_skill: Optional[str] = None,
    html_first: Optional[bool] = None,
    top_results: Optional[int] = None,
    use_browser: Optional[bool] = None,
    crawl_assist: Optional[bool] = None,
    crawl_pages: Optional[int] = None,
    strict: bool = False,
    command_name: str = "do-plan",
) -> Dict[str, Any]:
    compiled = agent.compile_task_ir(
        task=task,
        explicit_skill=explicit_skill,
        html_first=html_first,
        top_results=top_results,
        use_browser=use_browser,
        crawl_assist=crawl_assist,
        crawl_pages=crawl_pages,
        strict=strict,
        dry_run=True,
        command_name=command_name,
    )
    if not compiled.get("success"):
        return {
            "success": False,
            "error": compiled.get("error"),
            "compiled": compiled,
            "micro_skills": build_micro_skill_hints(command_name, task),
        }
    payload = agent._compose_playbook_from_compiled(task=task, compiled=compiled, strict=strict)
    if isinstance(payload, dict):
        payload["micro_skills"] = build_micro_skill_hints(command_name, task)
    return payload


async def execute_do_task(
    agent: "WebAgent",
    task: str,
    html_first: Optional[bool] = None,
    top_results: Optional[int] = None,
    use_browser: Optional[bool] = None,
    crawl_assist: Optional[bool] = None,
    crawl_pages: Optional[int] = None,
    strict: bool = False,
    dry_run: bool = False,
    explicit_skill: Optional[str] = None,
    command_name: str = "do",
) -> "AgentResponse":
    from agents.web_agent import AgentResponse

    compiled = agent.compile_task_ir(
        task=task,
        html_first=html_first,
        top_results=top_results,
        use_browser=use_browser,
        crawl_assist=crawl_assist,
        crawl_pages=crawl_pages,
        strict=strict,
        dry_run=dry_run,
        explicit_skill=explicit_skill,
        command_name=command_name,
    )
    if not compiled.get("success"):
        failed_data = dict(compiled) if isinstance(compiled, dict) else {"compiled": compiled}
        failed_data["micro_skills"] = build_micro_skill_hints(command_name, task)
        return AgentResponse(
            success=False,
            content=f"IR 编译失败：{compiled.get('error')}",
            error=str(compiled.get("error") or "compile_failed"),
            data=failed_data,
            metadata={"mode": "do", "command": command_name},
        )

    if dry_run or not compiled.get("valid"):
        playbook = agent._compose_playbook_from_compiled(task=task, compiled=compiled, strict=strict)
        if isinstance(compiled, dict):
            compiled["playbook"] = playbook
            compiled["micro_skills"] = build_micro_skill_hints(command_name, task)
        return AgentResponse(
            success=bool(compiled.get("valid")),
            content=(
                f"IR dry-run 完成：goal={task}\n"
                f"skill={compiled.get('ir', {}).get('skill')}\n"
                f"route={compiled.get('ir', {}).get('route')}\n"
                f"lint={compiled.get('lint', {}).get('error_count', 0)} errors / "
                f"{compiled.get('lint', {}).get('warning_count', 0)} warnings"
            ),
            data=compiled,
            error=(None if compiled.get("valid") else "ir_lint_failed"),
            metadata={"mode": "do_dry_run", "command": command_name},
        )

    spec = compiled["ir"]["workflow"]["spec"]
    response = await agent.run_workflow_spec(spec=spec, strict=strict)
    response.metadata.update(
        {
            "mode": "do",
            "command": command_name,
            "route": compiled["ir"].get("route"),
            "skill": compiled["ir"].get("skill"),
        }
    )
    if isinstance(response.data, dict):
        response.data["ir"] = compiled.get("ir")
        response.data["lint"] = compiled.get("lint")
        response.data["skill_resolution"] = compiled.get("skill_resolution")
        response.data["micro_skills"] = build_micro_skill_hints(command_name, task)
    response.content = (
        f"do 执行完成：{task}\n"
        f"skill={compiled['ir'].get('skill')} route={compiled['ir'].get('route')}\n\n"
        f"{response.content}"
    )
    return response

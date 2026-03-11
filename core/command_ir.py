"""
Command IR schema helpers.

The CLI compiles user intent to a stable intermediate representation (IR)
before execution, then lints IR/workflow for deterministic guardrails.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

IR_VERSION = "1.0"

_ALLOWED_ROUTES = {"auto", "general", "url", "social", "commerce", "academic"}
_TOKEN_PATTERN = re.compile(r"\$\{([^}]+)\}")
_ALLOWED_EXPR_PREFIX = ("vars", "steps", "last", "local", "env")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_command_ir(
    command: str,
    goal: str,
    route: str,
    workflow_spec: Dict[str, Any],
    options: Optional[Dict[str, Any]] = None,
    skill: Optional[str] = None,
    strict: bool = False,
    dry_run: bool = False,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "ir_version": IR_VERSION,
        "command": str(command or "do"),
        "goal": str(goal or ""),
        "route": str(route or "general"),
        "skill": str(skill or "default"),
        "strict": bool(strict),
        "dry_run": bool(dry_run),
        "options": dict(options or {}),
        "workflow": {
            "name": str(workflow_spec.get("name") if isinstance(workflow_spec, dict) else "workflow"),
            "spec": workflow_spec if isinstance(workflow_spec, dict) else {},
        },
        "metadata": dict(metadata or {}),
        "created_at": _utc_now_iso(),
    }


def lint_command_ir(
    ir: Dict[str, Any],
    workflow_schema: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    if not isinstance(ir, dict):
        _issue(issues, "error", "ir.not_object", "IR must be a JSON object", "$")
        return issues

    required_root_keys = ["ir_version", "command", "goal", "route", "workflow", "options"]
    for key in required_root_keys:
        if key not in ir:
            _issue(issues, "error", "ir.missing_key", f"Missing root key: {key}", f"$.{key}")

    ir_version = str(ir.get("ir_version") or "")
    if ir_version != IR_VERSION:
        _issue(
            issues,
            "warning",
            "ir.version_mismatch",
            f"IR version is {ir_version or 'empty'}, expected {IR_VERSION}",
            "$.ir_version",
        )

    command = str(ir.get("command") or "").strip()
    if not command:
        _issue(issues, "error", "ir.empty_command", "command must be non-empty", "$.command")

    goal = str(ir.get("goal") or "").strip()
    if not goal:
        _issue(issues, "error", "ir.empty_goal", "goal must be non-empty", "$.goal")

    route = str(ir.get("route") or "").strip().lower()
    if route not in _ALLOWED_ROUTES:
        _issue(
            issues,
            "warning",
            "ir.unknown_route",
            f"route '{route}' is not in known routes {_ALLOWED_ROUTES}",
            "$.route",
        )

    if not isinstance(ir.get("options"), dict):
        _issue(issues, "error", "ir.options_not_object", "options must be an object", "$.options")

    workflow = ir.get("workflow")
    if not isinstance(workflow, dict):
        _issue(issues, "error", "ir.workflow_not_object", "workflow must be an object", "$.workflow")
        return issues
    spec = workflow.get("spec")
    if not isinstance(spec, dict):
        _issue(issues, "error", "ir.spec_not_object", "workflow.spec must be an object", "$.workflow.spec")
        return issues

    issues.extend(lint_workflow_spec(spec=spec, workflow_schema=workflow_schema, root_path="$.workflow.spec"))
    return issues


def lint_workflow_spec(
    spec: Dict[str, Any],
    workflow_schema: Optional[Dict[str, Any]] = None,
    root_path: str = "$",
) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    if not isinstance(spec, dict):
        _issue(issues, "error", "workflow.not_object", "workflow spec must be an object", root_path)
        return issues

    steps = spec.get("steps")
    if not isinstance(steps, list) or not steps:
        _issue(issues, "error", "workflow.steps_empty", "workflow.steps must be a non-empty list", f"{root_path}.steps")
        return issues

    variables = spec.get("variables") if isinstance(spec.get("variables"), dict) else {}
    known_step_ids: Set[str] = set()
    known_tools: Set[str] = set()
    if isinstance(workflow_schema, dict):
        tool_map = workflow_schema.get("tools")
        if isinstance(tool_map, dict):
            known_tools = {str(key).strip().lower() for key in tool_map.keys() if str(key).strip()}

    for idx, step in enumerate(steps):
        path = f"{root_path}.steps[{idx}]"
        if not isinstance(step, dict):
            _issue(issues, "error", "workflow.step_not_object", "step must be an object", path)
            continue

        step_id = str(step.get("id") or "").strip()
        if not step_id:
            _issue(issues, "error", "workflow.step_missing_id", "step.id is required", f"{path}.id")
        elif step_id in known_step_ids:
            _issue(
                issues,
                "error",
                "workflow.step_id_duplicate",
                f"duplicate step id: {step_id}",
                f"{path}.id",
            )
        else:
            known_step_ids.add(step_id)

        tool = str(step.get("tool") or "").strip().lower()
        if not tool:
            _issue(issues, "error", "workflow.step_missing_tool", "step.tool is required", f"{path}.tool")
        elif known_tools and tool not in known_tools:
            _issue(
                issues,
                "error",
                "workflow.unknown_tool",
                f"unknown tool '{tool}', not present in schema",
                f"{path}.tool",
            )

        args = step.get("args", {})
        if args is None:
            args = {}
        if not isinstance(args, dict):
            _issue(issues, "error", "workflow.args_not_object", "step.args must be an object", f"{path}.args")
        else:
            _lint_placeholders(
                value=args,
                issues=issues,
                variables=variables,
                known_step_ids=known_step_ids,
                path=f"{path}.args",
            )

        for_each = step.get("for_each")
        if for_each is not None:
            if not isinstance(for_each, str):
                _issue(issues, "error", "workflow.for_each_not_string", "for_each must be a string expression", f"{path}.for_each")
            else:
                _lint_placeholders(
                    value=for_each,
                    issues=issues,
                    variables=variables,
                    known_step_ids=known_step_ids,
                    path=f"{path}.for_each",
                )
            item_alias = str(step.get("item_alias") or "").strip()
            if not item_alias:
                _issue(
                    issues,
                    "warning",
                    "workflow.item_alias_missing",
                    "for_each step without item_alias may reduce readability",
                    f"{path}.item_alias",
                )

    return issues


def has_lint_errors(issues: List[Dict[str, Any]]) -> bool:
    return any(str(item.get("level")) == "error" for item in issues if isinstance(item, dict))


def summarize_lint(issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    errors = 0
    warnings = 0
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        level = str(issue.get("level") or "").lower()
        if level == "error":
            errors += 1
        elif level == "warning":
            warnings += 1
    return {
        "valid": errors == 0,
        "error_count": errors,
        "warning_count": warnings,
        "issue_count": errors + warnings,
    }


def _lint_placeholders(
    value: Any,
    issues: List[Dict[str, Any]],
    variables: Dict[str, Any],
    known_step_ids: Set[str],
    path: str,
) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _lint_placeholders(item, issues, variables, known_step_ids, f"{path}.{key}")
        return
    if isinstance(value, list):
        for idx, item in enumerate(value):
            _lint_placeholders(item, issues, variables, known_step_ids, f"{path}[{idx}]")
        return
    if not isinstance(value, str):
        return

    for match in _TOKEN_PATTERN.finditer(value):
        expr = match.group(1).strip()
        if not expr:
            _issue(issues, "warning", "workflow.empty_placeholder", "empty placeholder expression", path)
            continue

        if expr.startswith("steps."):
            pieces = expr.split(".", 2)
            if len(pieces) >= 2:
                step_id = pieces[1]
                if step_id and step_id not in known_step_ids:
                    _issue(
                        issues,
                        "warning",
                        "workflow.forward_step_ref",
                        f"placeholder references step '{step_id}' before declaration",
                        path,
                    )
            continue

        if expr.startswith("vars."):
            var_name = expr[5:].split(".", 1)[0]
            if var_name and var_name not in variables:
                _issue(
                    issues,
                    "warning",
                    "workflow.undefined_var_ref",
                    f"placeholder references undefined variable '{var_name}'",
                    path,
                )
            continue

        if expr.startswith(_ALLOWED_EXPR_PREFIX):
            continue

        if expr not in variables:
            _issue(
                issues,
                "warning",
                "workflow.unknown_placeholder_ref",
                f"placeholder expression '{expr}' is not recognized",
                path,
            )


def _issue(
    issues: List[Dict[str, Any]],
    level: str,
    code: str,
    message: str,
    path: str,
) -> None:
    issues.append(
        {
            "level": level,
            "code": code,
            "message": message,
            "path": path,
        }
    )

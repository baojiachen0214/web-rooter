"""
Skill-level A/B regression harness.

Purpose:
- Compare two skills (or auto vs named skill) on the same task set.
- Support compile-only mode (IR/lint quality) and execute mode (real run).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import platform
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.web_agent import WebAgent


@dataclass
class ArmResult:
    arm: str
    score: float
    success: bool
    metrics: Dict[str, Any]
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "arm": self.arm,
            "score": round(self.score, 4),
            "success": self.success,
            "error": self.error,
            "metrics": self.metrics,
        }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_cases(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("cases"), list):
        cases = data["cases"]
    elif isinstance(data, list):
        cases = data
    else:
        raise ValueError("cases must be list or object with 'cases' list")

    normalized: List[Dict[str, Any]] = []
    for idx, item in enumerate(cases):
        if not isinstance(item, dict):
            continue
        goal = str(item.get("goal") or "").strip()
        if not goal:
            continue
        options = item.get("options") if isinstance(item.get("options"), dict) else {}
        normalized.append(
            {
                "id": str(item.get("id") or f"case_{idx + 1}"),
                "goal": goal,
                "options": options,
                "expected_skill": (str(item.get("expected_skill")).strip() if str(item.get("expected_skill") or "").strip() else None),
                "expected_route": (str(item.get("expected_route")).strip() if str(item.get("expected_route") or "").strip() else None),
            }
        )
    if not normalized:
        raise ValueError("no valid cases found")
    return normalized


def _extract_options(options: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "html_first": options.get("html_first"),
        "top_results": options.get("top_results"),
        "use_browser": options.get("use_browser"),
        "crawl_assist": options.get("crawl_assist"),
        "crawl_pages": options.get("crawl_pages"),
        "strict": bool(options.get("strict", False)),
    }


def _score_compile(metrics: Dict[str, Any]) -> float:
    valid = bool(metrics.get("valid"))
    errors = int(metrics.get("error_count", 0) or 0)
    warnings = int(metrics.get("warning_count", 0) or 0)
    return (100.0 if valid else 0.0) - errors * 25.0 - warnings * 2.0


def _score_execute(metrics: Dict[str, Any]) -> float:
    success = bool(metrics.get("success"))
    completed = int(metrics.get("completed_steps", 0) or 0)
    failed = int(metrics.get("failed_steps", 0) or 0)
    url_count = int(metrics.get("url_count", 0) or 0)
    duration_ms = int(metrics.get("duration_ms", 0) or 0)
    score = 0.0
    score += 120.0 if success else 0.0
    score += completed * 3.0
    score -= failed * 15.0
    score += min(url_count, 20)
    score -= min(duration_ms / 1000.0, 60.0) * 0.7
    return score


def _apply_expectation_bonus(
    result: ArmResult,
    expected_skill: Optional[str],
    expected_route: Optional[str],
) -> ArmResult:
    skill = str((result.metrics or {}).get("skill") or "")
    route = str((result.metrics or {}).get("route") or "")
    expected_skill_norm = str(expected_skill or "").strip()
    expected_route_norm = str(expected_route or "").strip()

    skill_match = True
    route_match = True
    if expected_skill_norm:
        skill_match = skill == expected_skill_norm
        result.score += 30.0 if skill_match else -30.0
    if expected_route_norm:
        route_match = route == expected_route_norm
        result.score += 20.0 if route_match else -20.0

    result.metrics["expected_skill"] = expected_skill_norm or None
    result.metrics["expected_route"] = expected_route_norm or None
    result.metrics["skill_match"] = skill_match
    result.metrics["route_match"] = route_match
    return result


async def _run_arm_compile(
    agent: WebAgent,
    goal: str,
    skill: Optional[str],
    options: Dict[str, Any],
    arm_name: str,
) -> ArmResult:
    compiled = agent.compile_task_ir(
        task=goal,
        explicit_skill=skill,
        dry_run=True,
        command_name=f"ab_compile_{arm_name}",
        **_extract_options(options),
    )
    if not compiled.get("success"):
        return ArmResult(
            arm=arm_name,
            score=-999.0,
            success=False,
            error=str(compiled.get("error") or "compile_failed"),
            metrics={"valid": False, "error_count": 1, "warning_count": 0},
        )

    lint = compiled.get("lint") if isinstance(compiled.get("lint"), dict) else {}
    metrics = {
        "valid": bool(compiled.get("valid")),
        "error_count": int(lint.get("error_count", 0) or 0),
        "warning_count": int(lint.get("warning_count", 0) or 0),
        "skill": ((compiled.get("ir") or {}).get("skill") if isinstance(compiled.get("ir"), dict) else None),
        "route": ((compiled.get("ir") or {}).get("route") if isinstance(compiled.get("ir"), dict) else None),
    }
    return ArmResult(
        arm=arm_name,
        score=_score_compile(metrics),
        success=bool(metrics["valid"]),
        metrics=metrics,
    )


async def _run_arm_execute(
    agent: WebAgent,
    goal: str,
    skill: Optional[str],
    options: Dict[str, Any],
    arm_name: str,
) -> ArmResult:
    response = await agent.run_do_task(
        task=goal,
        explicit_skill=skill,
        dry_run=False,
        command_name=f"ab_execute_{arm_name}",
        **_extract_options(options),
    )
    data = response.data if isinstance(response.data, dict) else {}
    reports = data.get("reports") if isinstance(data.get("reports"), list) else []
    completed_steps = sum(
        1 for item in reports if isinstance(item, dict) and item.get("status") in {"completed", "soft_failed"}
    )
    failed_steps = sum(1 for item in reports if isinstance(item, dict) and item.get("status") == "failed")
    metrics = {
        "success": bool(response.success),
        "duration_ms": int(data.get("duration_ms", 0) or 0),
        "completed_steps": completed_steps,
        "failed_steps": failed_steps,
        "url_count": len(data.get("urls", []) if isinstance(data.get("urls"), list) else []),
        "skill": ((data.get("ir") or {}).get("skill") if isinstance(data.get("ir"), dict) else None),
        "route": ((data.get("ir") or {}).get("route") if isinstance(data.get("ir"), dict) else None),
    }
    return ArmResult(
        arm=arm_name,
        score=_score_execute(metrics),
        success=bool(response.success),
        metrics=metrics,
        error=response.error,
    )


async def run(
    cases_path: Path,
    arm_a: str,
    arm_b: str,
    execute: bool,
    max_cases: Optional[int],
    case_timeout_sec: float,
    json_out: Path,
    md_out: Path,
) -> Dict[str, Any]:
    cases = _load_cases(cases_path)
    if isinstance(max_cases, int) and max_cases > 0:
        cases = cases[: max_cases]

    timeout_value = float(case_timeout_sec or 0.0)
    timeout_enabled = timeout_value > 0.0

    async def run_arm_with_timeout(coro, arm_name: str) -> ArmResult:
        if not timeout_enabled:
            return await coro
        try:
            return await asyncio.wait_for(coro, timeout=timeout_value)
        except asyncio.TimeoutError:
            return ArmResult(
                arm=arm_name,
                score=-999.0,
                success=False,
                error=f"timeout>{timeout_value:.1f}s",
                metrics={
                    "timeout_sec": timeout_value,
                    "valid": False,
                    "error_count": 1,
                    "warning_count": 0,
                    "success": False,
                    "completed_steps": 0,
                    "failed_steps": 1,
                    "url_count": 0,
                    "duration_ms": int(timeout_value * 1000),
                },
            )

    agent = WebAgent()
    await agent._init()
    try:
        case_reports: List[Dict[str, Any]] = []
        wins = {"A": 0, "B": 0, "tie": 0}

        for case in cases:
            goal = case["goal"]
            options = case.get("options") if isinstance(case.get("options"), dict) else {}
            expected_skill = case.get("expected_skill")
            expected_route = case.get("expected_route")

            if execute:
                res_a = await run_arm_with_timeout(
                    _run_arm_execute(agent, goal, None if arm_a == "auto" else arm_a, options, "A"),
                    "A",
                )
                res_b = await run_arm_with_timeout(
                    _run_arm_execute(agent, goal, None if arm_b == "auto" else arm_b, options, "B"),
                    "B",
                )
            else:
                res_a = await run_arm_with_timeout(
                    _run_arm_compile(agent, goal, None if arm_a == "auto" else arm_a, options, "A"),
                    "A",
                )
                res_b = await run_arm_with_timeout(
                    _run_arm_compile(agent, goal, None if arm_b == "auto" else arm_b, options, "B"),
                    "B",
                )
            res_a = _apply_expectation_bonus(res_a, expected_skill=expected_skill, expected_route=expected_route)
            res_b = _apply_expectation_bonus(res_b, expected_skill=expected_skill, expected_route=expected_route)

            if abs(res_a.score - res_b.score) <= 1e-8:
                winner = "tie"
            elif res_a.score > res_b.score:
                winner = "A"
            else:
                winner = "B"
            wins[winner] += 1

            case_reports.append(
                {
                    "id": case["id"],
                    "goal": goal,
                    "options": options,
                    "expected_skill": expected_skill,
                    "expected_route": expected_route,
                    "winner": winner,
                    "A": res_a.to_dict(),
                    "B": res_b.to_dict(),
                }
            )
    finally:
        await agent.close()

    overall = "tie"
    if wins["A"] > wins["B"]:
        overall = "A"
    elif wins["B"] > wins["A"]:
        overall = "B"

    report = {
        "timestamp_utc": _utc_now_iso(),
        "python": sys.version.replace("\n", " "),
        "platform": f"{platform.system()} {platform.release()}",
        "mode": ("execute" if execute else "compile"),
        "arms": {"A": arm_a, "B": arm_b},
        "max_cases": (max_cases if isinstance(max_cases, int) and max_cases > 0 else None),
        "case_timeout_sec": (timeout_value if timeout_enabled else None),
        "wins": wins,
        "overall_winner": overall,
        "cases": case_reports,
    }

    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_out.write_text(_to_markdown(report), encoding="utf-8")
    return report


def _to_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Skill A/B Regression")
    lines.append("")
    lines.append(f"- Timestamp (UTC): {report.get('timestamp_utc')}")
    lines.append(f"- Mode: {report.get('mode')}")
    lines.append(f"- Arm A: {report.get('arms', {}).get('A')}")
    lines.append(f"- Arm B: {report.get('arms', {}).get('B')}")
    if report.get("max_cases"):
        lines.append(f"- Max Cases: {report.get('max_cases')}")
    if report.get("case_timeout_sec"):
        lines.append(f"- Case Timeout Sec: {report.get('case_timeout_sec')}")
    lines.append(f"- Wins: {report.get('wins')}")
    lines.append(f"- Overall Winner: **{report.get('overall_winner')}**")
    lines.append("")

    for case in report.get("cases", []):
        lines.append(f"## {case.get('id')}")
        lines.append("")
        lines.append(f"- Goal: {case.get('goal')}")
        if case.get("expected_skill"):
            lines.append(f"- Expected Skill: `{case.get('expected_skill')}`")
        if case.get("expected_route"):
            lines.append(f"- Expected Route: `{case.get('expected_route')}`")
        lines.append(f"- Winner: **{case.get('winner')}**")
        lines.append(f"- A: score={case.get('A', {}).get('score')} success={case.get('A', {}).get('success')}")
        lines.append(f"- B: score={case.get('B', {}).get('score')} success={case.get('B', {}).get('success')}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run skill A/B regression for web-rooter")
    parser.add_argument(
        "--cases",
        default="profiles/skills/ab_cases.template.json",
        help="Path to skill AB cases JSON",
    )
    parser.add_argument("--arm-a", default="auto", help="Skill name for arm A, or 'auto'")
    parser.add_argument("--arm-b", default="social_comment_mining", help="Skill name for arm B, or 'auto'")
    parser.add_argument("--execute", action="store_true", help="Run real execution instead of compile-only")
    parser.add_argument("--max-cases", type=int, default=0, help="Max number of cases to run (0 means all)")
    parser.add_argument("--case-timeout-sec", type=float, default=0.0, help="Per-arm timeout seconds (0 disables timeout)")
    parser.add_argument(
        "--json-out",
        default=f"temp/skill_ab_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        help="JSON report output path",
    )
    parser.add_argument(
        "--md-out",
        default=f"temp/skill_ab_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
        help="Markdown report output path",
    )
    args = parser.parse_args()

    report = asyncio.run(
        run(
            cases_path=Path(args.cases).resolve(),
            arm_a=args.arm_a,
            arm_b=args.arm_b,
            execute=bool(args.execute),
            max_cases=(args.max_cases if int(args.max_cases or 0) > 0 else None),
            case_timeout_sec=float(args.case_timeout_sec or 0.0),
            json_out=Path(args.json_out).resolve(),
            md_out=Path(args.md_out).resolve(),
        )
    )
    print(
        json.dumps(
            {
                "overall_winner": report.get("overall_winner"),
                "wins": report.get("wins"),
                "mode": report.get("mode"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

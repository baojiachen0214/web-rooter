from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.ai_tool_skills import doctor_skills, install_skills, register_skills_dir
from core.micro_skills import build_micro_skill_hints


class AIToolSkillsTests(unittest.TestCase):
    def test_install_skills_writes_canonical_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            (repo_root / "main.py").write_text("# stub\n", encoding="utf-8")
            result = install_skills(repo_root=repo_root, include_home=False)
            files = result.get("files")
            self.assertIsInstance(files, list)
            created_paths = {Path(item["path"]).relative_to(repo_root).as_posix() for item in files if isinstance(item, dict)}
            self.assertIn(".claude/skills/web-rooter/SKILL.md", created_paths)
            self.assertIn("AGENTS.md", created_paths)
            self.assertIn(".agents/skills/web-rooter/SKILL.md", created_paths)

    def test_register_custom_skills_dir_and_doctor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            (repo_root / "main.py").write_text("# stub\n", encoding="utf-8")
            custom_dir = repo_root / "custom-skills"
            payload = register_skills_dir(repo_root, str(custom_dir), tool="claude", write_now=True)
            self.assertTrue(payload.get("success"))
            target_path = Path(str(payload.get("target_path")))
            self.assertTrue(target_path.exists())

            report = doctor_skills(repo_root, include_home=False)
            checks = report.get("checks")
            self.assertIsInstance(checks, list)
            self.assertTrue(any(isinstance(item, dict) and str(item.get("path")) == str(target_path) for item in checks))

            config_path = repo_root / ".web-rooter" / "ai-skills" / "config.json"
            data = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertTrue(any(str(item.get("path")) == str(custom_dir) for item in data.get("custom_targets", [])))

    def test_micro_skill_hints_match_social_detail(self) -> None:
        hints = build_micro_skill_hints("do-plan", "读取这个小红书帖子正文和评论区")
        self.assertIsInstance(hints, list)
        self.assertGreaterEqual(len(hints), 1)
        top = hints[0]
        self.assertIn("prefer_tools", top)
        self.assertTrue(any(tool in top.get("prefer_tools", []) for tool in ["do", "social", "auth-hint"]))


if __name__ == "__main__":
    unittest.main()

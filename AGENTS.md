# Web-Rooter Agent Skill Pack

This file is managed by Web-Rooter skill installers.

# Web-Rooter CLI Skills

## Goal
- Treat Web-Rooter as a CLI-first orchestration layer.
- Prefer staged usage: `wr skills --resolve` -> `wr do-plan` -> `wr do --dry-run` -> `wr do`.
- Avoid using low-level commands (`crawl`, `extract`, `site`) as the first step for detail-page tasks.

## Fast Route
1. Resolve skill:
   - `wr skills --resolve "<goal>" --compact`
2. Get staged playbook:
   - `wr do-plan "<goal>"`
3. Compile and lint:
   - `wr do "<goal>" --dry-run`
4. Execute:
   - `wr do "<goal>"`

## Platform Notes
- Social detail pages (小红书 / Bilibili / 知乎 / 微博): prefer `wr do` or `wr social`; surface `wr auth-hint <url>` first when login may matter.
- Academic tasks: prefer `wr academic` or `wr do --skill=academic_relation_mining`.
- Commerce review tasks: prefer `wr shopping` or `wr do --skill=commerce_review_mining`.
- Long jobs: prefer `wr do-submit`, then inspect with `wr jobs` / `wr job-status <id>`.

## High-Signal Commands
- `wr help`
- `wr doctor`
- `wr skills --resolve "<goal>" --compact`
- `wr do-plan "<goal>"`
- `wr do "<goal>" --dry-run`
- `wr do "<goal>"`
- `wr auth-hint <url>`
- `wr add-skills-dir <path> --tool=<tool>`
- `wr skills-install`

## Repo
- Root: `/Users/jiachen/Projects/ai/web-rooter`
- Primary docs: `README.md`, `README.zh-CN.md`, `docs/guide/CLI.md`


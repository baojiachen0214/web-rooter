# Skill Contracts

`profiles/skills/*.json` 定义 AI 可选的抓取技能契约。

设计目标：
- CLI 只暴露一个主入口（`do`），但行为可通过 skill 配置演化
- 不把站点脚本写死到代码里，优先“意图 -> skill -> workflow/策略”
- 支持外部 AI 在不同上下文长度下稳定选择正确执行路径

关键字段：
- `name`: skill 唯一标识
- `route`: `auto|general|url|social|commerce|academic`
- `workflow_template`: 可选，映射到 `core.workflow.build_workflow_template`
- `intent_keywords`: 意图匹配关键词（用于自动路由）
- `activation_keywords`: 激活关键词（命中不足时即使有分数也不会选中该 skill）
- `min_activation_hits`: 最小激活命中数（默认 `0`）
- `min_score`: 最小分数阈值（默认 `0.0`）
- `default_variables`: 注入 workflow 变量默认值
- `default_options`: 执行选项默认值（如 `html_first`/`crawl_assist`/`top_results`）
- `phases`: 阶段化执行剧本（供 `do-plan` 返回给 AI）

可选实践：
- 为每个 skill 维护最少 2 条 `examples`，作为外层 AI 提示样例
- 对登录门槛站点，配合 `auth-hint`/`auth-template` 提供前置提示
- 对“泛词高频误判”场景（如“讨论”“趋势”），尽量放在 `intent_keywords` 而非 `activation_keywords`

A/B 回归建议：
- `profiles/skills/ab_cases.template.json` 支持 `expected_skill` 和 `expected_route`
- `scripts/regression/run_skill_ab.py` 会把技能/路由命中奖励计入评分，直接量化“路由是否选对”

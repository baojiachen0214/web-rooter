from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


SKILL_MARKER = "Web-Rooter CLI Skills"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _config_dir(repo_root: Optional[Path] = None) -> Path:
    root = (repo_root or _project_root()).resolve()
    return root / ".web-rooter" / "ai-skills"


def _config_path(repo_root: Optional[Path] = None) -> Path:
    return _config_dir(repo_root) / "config.json"


@dataclass(frozen=True)
class InstallTarget:
    tool: str
    path: Path
    content_kind: str
    origin: str = "builtin"


def _write_text(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old == content:
        return "unchanged"
    path.write_text(content, encoding="utf-8")
    return "updated" if old is not None else "created"


def _load_config(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    path = _config_path(repo_root)
    if not path.exists():
        return {"custom_targets": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"custom_targets": []}
    if not isinstance(data, dict):
        return {"custom_targets": []}
    custom = data.get("custom_targets")
    if not isinstance(custom, list):
        data["custom_targets"] = []
    return data


def _save_config(config: Dict[str, Any], repo_root: Optional[Path] = None) -> Path:
    path = _config_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _skill_markdown(repo_root: Path) -> str:
    repo_text = str(repo_root.resolve())
    return f"""# {SKILL_MARKER}

> 这不是命令参考，而是认知框架。阅读后，你应该理解的是"如何像 WR 专家一样思考"，而非"WR 有哪些命令"。

## ⚠️ 核心要点速查（使用 WR 前必看）

### 🚨 绝对不能忘的三件事
```
1. 【环境检查】任何任务前 → wr doctor
2. 【认证检查】平台任务前 → wr auth-hint <URL> → 如需登录 → wr cookie <平台>
3. 【错误处理】遇到问题时 → wr help <命令> 或 wr doctor
```

### 🎯 工具选择速查表
```
任务类型                    正确命令                          禁用
─────────────────────────────────────────────────────────────────────────
学术文献搜索               wr academic "query"               wr do "搜索论文"
社交平台内容               wr social "query" --platform=xxx  wr do "小红书..."
电商平台内容               wr shopping "query"               wr do "淘宝..."
技术社区内容               wr tech "query"                   wr do "GitHub..."
简单网页访问               wr html <URL> [--js]              wr do "访问..."
深度多源研究               wr deep "query"                   wr do "深度研究..."
复杂多步骤编排             wr do "任务"（最后手段）          不要滥用
```

### ⚡ 关键概念：wr do 的输入质量
```
【核心认知】do 的输出质量 100% 依赖输入质量

❌ 模糊输入: "分析一下小红书"
   → do planner 迷茫 → 生成错误 workflow → 失败

✅ 清晰输入: "分析小红书帖子 https://xhs.link/abc 的正文和前10条评论"
   → do planner 精准理解 → 生成正确 workflow → 成功

【使用 do 前必须完成】
□ 明确具体 URL 或搜索范围
□ 明确要获取什么数据（正文？评论？标题？）
□ 明确数量限制（前10条？前50条？）
□ 明确输出格式（列表？表格？段落？）
□ 检查认证（wr auth-hint）
□ 先用 wr do-plan 验证理解是否正确
```

### 🔥 常见错误防范
```
错误 1: 忘记 wr doctor
  症状: 命令执行失败，提示依赖缺失/浏览器未安装
  防范: 任务开始前强制执行 wr doctor

错误 2: 忘记 wr cookie
  症状: 平台返回 403/登录框/内容为空
  防范: 任何平台任务前先 wr auth-hint，提示登录就 wr cookie

错误 3: 滥用 wr do
  症状: 简单任务用 do，结果复杂化且失败
  防范: 能用专用工具就不用 do（academic/social/shopping/html）

错误 4: 不看 completion
  症状: 任务显示成功但实际数据缺失
  防范: 执行后检查 completion 字段，确认 required_outputs 都满足

错误 5: 遇到错误瞎猜
  症状: "可能是...让我试试..."
  防范: 第一时间 wr help 或 wr doctor，不要凭记忆瞎编
```

---

## 核心认知原则

### 原则 1: 强制诊断优先
**违反此原则的 AI 行为**: 直接开始爬取，不检查环境是否就绪
**正确认知**:
```
任何任务开始前 → 必须先执行 wr doctor
遇到异常失败时 → 必须重新执行 wr doctor
长时间未使用 WR 后 → 必须执行 wr doctor
```
**原因**: WR 依赖浏览器、网络、认证配置，这些状态会变化。不知道当前状态就执行，如同蒙眼开车。

### 原则 2: 分层任务分解
**违反此原则的 AI 行为**: 无论什么任务都直接用 `wr do`
**正确认知**:
```
任务类型判断:
  ├─ 需要特定平台认证? → wr auth-hint → wr cookie → 再执行
  ├─ 纯学术文献检索? → wr academic (不需要 do)
  ├─ 电商比价/评价? → wr shopping (不需要 do)
  ├─ 简单单页访问? → wr visit / wr html (不需要 do)
  ├─ 深度多源研究? → wr deep / wr mindsearch (不需要 do)
  └─ 复杂多步骤任务? → wr do (最后才用)
```

### 原则 3: 渐进式执行
**违反此原则的 AI 行为**: 直接 `wr do "任务" --strict`
**正确认知**:
```
复杂任务必须分阶段:
  Stage 1: wr skills --resolve "任务" --compact
    → 理解 WR 推荐的处理方式
    → 获取 micro_skills 提示

  Stage 2: wr do-plan "任务"
    → 查看生成的执行计划
    → 判断是否拆解不够/工具选择错误
    → 如果不满意，调整目标重新 plan

  Stage 3: wr do "任务" --dry-run
    → 验证 IR 编译是否通过
    → 检查 lint 错误
    → 确认参数传递正确

  Stage 4: wr do "任务" --strict
    → 正式执行
    → 检查 completion 结果
    → 如果不完整，分析缺失项
```

### 原则 4: 失败即诊断
**违反此原则的 AI 行为**: "爬取失败了，我换个方式再试试"
**正确认知**:
```
任何失败后必须执行:
  1. wr doctor → 检查基础环境
  2. wr auth-hint <失败的URL> → 检查认证状态
  3. wr context --limit=20 → 查看最近的执行痕迹
  4. 分析失败模式:
     - 403/401? → 认证问题 → wr cookie 更新
     - timeout? → 网络问题 → 检查网络/代理
     - empty result? → 选择器问题 → 检查 --js 参数
     - partial complete? → completion contract 未满足 → 调整参数重试
```

### 原则 5: 专用工具优先
**违反此原则的 AI 行为**: 用 `wr do "搜索小红书"` 而不是 `wr social`
**正确认知**:
```
每个垂直领域都有专用工具，它们在处理该领域问题时优于通用 do:

学术领域:
  ✗ wr do "搜索 RAG 论文"
  ✓ wr academic "RAG" --papers-only --source=arxiv,google_scholar

社交平台:
  ✗ wr do "小红书 iPhone 评测"
  ✓ wr social "iPhone 评测" --platform=xiaohongshu,zhihu

电商平台:
  ✗ wr do "淘宝 iPhone 价格"
  ✓ wr shopping "iPhone" --platform=taobao,jd

技术社区:
  ✗ wr do "React 最佳实践"
  ✓ wr tech "React best practices" --source=github,stackoverflow
```

### 原则 6: 分层检索与阅读 - 不要上来就全文
**违反此原则的 AI 行为**: 拿到文档就从头到尾阅读，不管用户需要什么
**正确认知**:
```
【核心原则】不是"拿到就读"，而是"按需索取"

分层阅读决策模型:

Level 0: 元数据层（标题、作者、关键词）
  用途: 快速筛选相关性
  场景: "找找有没有关于 XXX 的论文"
  工具: wr academic（只返回元数据，不读全文）
  时间: 秒级

Level 1: 摘要层（Abstract）
  用途: 判断论文是否值得深入
  场景: "这篇论文讲什么？" "和我要的问题相关吗？"
  工具: wr academic（返回摘要）
  时间: 秒级

Level 2: 结构层（目录、章节标题）
  用途: 定位感兴趣的部分
  场景: "论文的方法部分在哪里？"
  工具: wr html <URL> --max-chars=30000（快速扫描结构）
  时间: 秒级

Level 3: 精确检索层（关键词定位）
  用途: 找特定内容是否存在于文中
  场景: "论文中有没有提到 'attention mechanism'？"
  工具: 浏览器页面内搜索 / 文本检索
  策略: 加载页面后用 Ctrl+F 思路定位关键词
  时间: 秒级

#### 结构感知阅读实战：利用 WR 先探结构，再选择性深入
```
【核心认知】WR 的爬虫能力不只是"下载全文"，更是"结构探测"

实战流程：获取论文 → 探测结构 → 选择性阅读

Step 1: 快速获取论文结构（不解码全文）
  命令: wr html https://arxiv.org/html/1706.03762 --max-chars=30000
  目的: 不看内容，只看"骨架"
  关注:
    - 章节标题（Introduction, Method, Experiments...）
    - 子章节分布
    - 图表位置标记
    - 参考文献数量
  时间: 5-10 秒

Step 2: 根据任务需求，定位目标章节
  示例任务: "论文用了什么优化器？"
  分析: 优化器信息通常在 Method 或 Experiments 部分
  行动: 在获取的结构中快速找到 "Method" / "Experimental Setup" 位置

Step 3: 精准提取目标章节内容
  策略 1: 再次 wr html，但只获取目标区域
    - 如果 URL 支持锚点: https://arxiv.org/html/1706.03762#section-3
    - 或使用 wr extract 定位特定章节
  
  策略 2: 使用 wr extract 直接提取
    命令: wr extract https://arxiv.org/html/1706.03762 "提取 Methods 章节的内容，关注优化器设置"

Step 4: 在局部内容中精读
  - 现在只需要处理几千字，而不是几万字
  - 搜索关键词 "optimizer", "Adam", "SGD" 等
  - 快速定位答案

对比：
  ❌ 线性阅读: 下载 5 万字全文 → 从头到尾读 → 找到优化器信息（30 分钟）
  ✅ 结构感知: 获取结构（10 秒）→ 定位 Method 章节 → 提取精读（2 分钟）

【WR 结构探测能力清单】

能力 1: 获取目录/大纲
  工具: wr html <URL> --max-chars=20000
  技巧: 大多数论文前 20KB 包含完整的目录和章节标题
  目的: 建立论文的"地图"

能力 2: 提取链接和引用
  工具: wr links <URL>
  用途: 
    - 论文内部的章节跳转链接
    - 引用的其他论文链接
    - 相关资源链接
  价值: 通过引用网络快速了解论文的上下文

能力 3: 章节级定位
  工具: wr extract <URL> "目标章节"
  示例:
    wr extract https://arxiv.org/html/... "提取 Related Work 部分"
    wr extract https://arxiv.org/html/... "提取 Table 2 和它的说明文字"

能力 4: 关键词预扫描
  工具: wr html <URL> | grep -i "关键词"
  用途: 快速判断论文是否包含感兴趣的内容
  示例: 先扫一遍是否提到 "GPT", "BERT", "transformer"
  如果都没提到 → 可能不相关，跳过

【典型场景：智能阅读决策树】

场景: "读这篇论文，告诉我它的创新点"

决策流程:
  1. 获取元数据
     wr academic "论文标题" → 看摘要
     判断: 和我的问题相关吗？
     如果不相关 → 放弃，换一篇

  2. 获取结构（如果摘要相关）
     wr html <URL> --max-chars=20000
     扫描: 找到 "Introduction" 和 "Conclusion"
     为什么？创新点通常在 Intro 的问题陈述和 Conclusion 的贡献总结中

  3. 提取关键章节
     wr extract <URL> "Introduction 章节的前三段"
     wr extract <URL> "Conclusion 或 Discussion 章节"
     阅读: 这两部分通常包含完整的创新点描述

  4. 验证（如果需要）
     如果 Intro/Conclusion 提到特定技术细节 → 再提取 Method 相关部分
     不是一开始就读 Method！

场景: "论文的实验用了什么数据集？"

决策流程:
  1. 直接定位
     数据集信息通常在 "Experiments" / "Experimental Setup" / "Evaluation"
     
  2. 提取实验章节
     wr extract <URL> "Experimental Setup 或 Datasets 部分"
     
  3. 搜索关键词
     在提取的内容中搜索 "dataset", "data", "benchmark"
     找到具体数据集名称

  4. 不需要读
     - 不需要读 Introduction 的理论背景
     - 不需要读 Related Work 的文献综述
     - 不需要读 Conclusion 的未来工作

【记忆口诀】
  "先探结构不盲读，按需索取省时间
   目录章节先扫描，目标定位再深入
   WR 不只是下载器，更是智能探测器"
```

Level 4: 局部精读层（相关段落）
  用途: 深入理解特定部分
  场景: "仔细读一下实验设置部分"
  工具: wr html <URL> --max-chars=100000 + 定位到章节
  时间: 分钟级

Level 5: 全文精读层（完整阅读）
  用途: 全面理解、复现、深度分析
  场景: "详细总结这篇论文的所有贡献"
  工具: wr html <URL> --max-chars=200000
  时间: 十分钟级以上

【关键决策点】
每次拿到文档前，先问:
  1. 用户要什么级别的信息？
     - 只是"有没有"→ Level 0/1 就够了
     - 要"具体内容"→ 需要 Level 3/4
     - 要"全面理解"→ 才需要 Level 5

  2. 能不能先过滤再深入？
     ✓ 先读摘要，相关才继续
     ✓ 先搜索关键词，命中才精读
     ✗ 不要上来就 --max-chars=200000

  3. 是否需要多篇对比？
     - 如果是 → 每篇都只读 Level 1，筛选后再精读
     - 不要每篇都 Level 5，时间成本爆炸
```

#### 智能检索策略（针对"验证观点是否存在"类任务）
```
用户问: "Transformer 的 'attention is all you need' 这个观点最早出自哪里？"

❌ 错误做法:
  直接搜索 "Attention is All You Need" 论文
  下载全文，从头到尾阅读
  回答: "出自这篇论文"
  问题: 没有验证是否真的是"最早"

✅ 正确做法:
  Step 1: 问题拆解
    - 需要确认什么？"attention is all you need" 这个观点
    - 时间维度？"最早"意味着需要查前序工作
    - 范围？自然语言处理领域

  Step 2: 制定检索策略
    - 搜索关键词: "attention mechanism NLP history", "before transformer attention"
    - 目标: 找到 Transformer 之前的 attention 相关工作
    - 深度: 先看标题和摘要（Level 0/1）

  Step 3: 分层检索
    wr academic "attention mechanism neural machine translation"
    → 获取 5-10 篇相关论文的标题和摘要
    → 快速浏览判断时间顺序
    → 发现 "Neural Machine Translation by Jointly Learning to Align and Translate" (2015, Bahdanau)

  Step 4: 精确定位
    wr html https://arxiv.org/html/1409.0473 --max-chars=50000
    → 搜索 "attention" 关键词在文中的论述
    → 确认这是较早提出 attention 机制的论文

  Step 5: 验证结论
    "attention is all you need" 实际上是 Transformer 论文的口号
    但 attention 机制本身最早来自 Bahdanau et al. 2015
    需要区分 "概念首创" 和 "口号提出"

【策略总结】
验证观点类任务的标准流程:
  1. 拆解问题: 观点是什么？时间范围？领域？
  2. 制定检索: 选择关键词、工具、深度
  3. 分层执行: 元数据→摘要→关键词定位→局部精读
  4. 交叉验证: 多源确认，避免单一证据
  5. 给出结论: 明确区分"首创""引用""发展"
```

#### 任务拆解与自我规划框架
```
接到任务后，AI 必须制定执行计划:

【规划模板】

任务: _______________

问题拆解:
  1. 核心问题是什么？
  2. 需要哪些信息来回答？
  3. 信息可能在哪里？（论文？网页？数据库？）
  4. 时间范围？（最新？历史？特定时期？）
  5. 精度要求？（大致了解？精确引用？全面综述？）

检索策略:
  - 关键词列表: ______, ______, ______
  - 工具选择: ______
  - 检索深度: Level __（元数据/摘要/全文）
  - 数量限制: 前 __ 篇

执行计划:
  Phase 1: ______（如：快速筛选相关论文）
    - 工具: ______
    - 成功标准: ______
    - 失败处理: ______

  Phase 2: ______（如：深入阅读核心论文）
    - 工具: ______
    - 成功标准: ______

  Phase 3: ______（如：验证和交叉对比）
    - 工具: ______

动态调整触发条件:
  - 如果 Phase 1 找不到相关文献 → 调整关键词，扩大搜索范围
  - 如果找到太多文献 → 增加筛选条件，优先高引论文
  - 如果摘要不够回答 → 提升到 Level 4 局部精读
  - 如果局部信息矛盾 → 提升到 Level 5 全文理解

【示例】
用户: "RAG 技术中，哪种检索方法在 2024 年最受欢迎？"

AI 内部规划:
  问题拆解:
    - 核心: RAG 的检索方法
    - 时间: 2024 年（最近一年）
    - 指标: "最受欢迎"（需要看引用量、讨论热度）
    - 范围: 学术论文 + 技术博客 + 开源实现

  检索策略:
    - 关键词: "RAG retrieval method 2024", "RAG survey 2024", "retrieval augmented generation ranking"
    - 工具: wr academic（学术）+ wr tech（技术社区）
    - 深度: Level 1（先看摘要筛选）
    - 数量: 各 10 篇

  执行计划:
    Phase 1: 快速扫描
      - wr academic "RAG survey 2024" --source=arxiv
      - wr tech "RAG best practices 2024"
      - 目标: 找到提及检索方法比较的文献

    Phase 2: 深入分析
      - 对找到的核心论文，局部阅读方法部分
      - wr html <paper_url> --max-chars=50000
      - 提取具体检索方法名称和评估结果

    Phase 3: 验证热度
      - wr deep "RAG dense retrieval vs sparse retrieval 2024"
      - 对比不同来源的观点是否一致

  动态调整:
    - 如果学术文献太理论 → 增加 wr tech 获取更多工程实践
    - 如果 2024 年文献太少 → 扩展到 2023 年底的预印本
```

### 原则 7: 第一性原理拆解用户意图
**违反此原则的 AI 行为**: 表面理解用户词汇，不深挖真实需求
**正确认知**:
```
用户说的话 ≠ 用户真正想要的
必须通过"目的-手段-交付"三层模型拆解

拆解框架（每次接到任务必问）:

1. 用户的最终目的是什么？
   - 是要"知道"（获取信息）？
   - 还是要"使用"（分析处理）？
   - 还是要"展示"（生成报告）？

2. 需要的深度是多少？
   - 浅层: 知道存在即可（返回链接/标题）
   - 中层: 了解概要（阅读摘要/目录）
   - 深层: 完全理解（阅读全文+分析）

3. 交付物应该是什么形式？
   - 原始数据（让用户自己看）
   - 加工信息（总结、对比）
   - 可直接使用的输出（表格、引用）
```

#### 语义解码词典
```
用户说 "找/查/搜索" → 通常是 Level 1（定位）
  例: "找 Transformer 论文"
  理解: 用户要的是"论文在哪"，不是论文内容
  行动: 返回 arXiv 链接即可，不要自动读取全文

用户说 "读/看/了解" → 需要判断深度
  例: "读一下这篇论文"（模糊）
  必须追问或判断:
    - 如果只是了解背景 → 读摘要即可
    - 如果要理解方法 → 读全文
    - 如果要复现 → 还需要代码

用户说 "分析/总结/提取" → 必须是 Level 2+（全文）
  例: "分析论文的创新点"
  理解: 必须获取全文内容，不能只读摘要
  行动: 访问 HTML 版全文，而非 abs 页

用户说 "对比/比较" → 需要多源
  例: "对比两篇论文"
  理解: 需要获取两篇的全文，分别分析后再对比
  行动: 不要试图一次 wr do 完成，分两次获取再人工分析

用户说 "获取/爬/抓" → 需要明确数据粒度
  例: "获取小红书的评论"
  理解: 
    - 要多少条？（10条 vs 1000条）
    - 要什么字段？（内容+作者+时间？）
    - 要原始数据还是分析结果？
```

#### 意图揣测的五个维度
```
接到任务时，从这五个维度分析:

Dimension 1: 范围 (Scope)
  "研究 AI" → 太广，需要缩小
  "研究 Transformer 架构" → 合适
  "研究 Transformer 的注意力机制" → 很具体

Dimension 2: 深度 (Depth)
  "了解大概" → 摘要/综述即可
  "深入理解" → 需要全文+相关资料
  "成为专家" → 需要系列论文+代码+实践

Dimension 3: 时效 (Timeliness)
  "最新进展" → 优先 2023-2024 年论文
  "经典方法" → 找开创性论文（如 2017 Transformer）
  "发展历程" → 需要按时间线梳理

Dimension 4: 格式 (Format)
  "给我链接" → 返回 URL 列表
  "总结给我" → 需要阅读后输出文本
  "做张表格" → 结构化提取
  "给出引用" → 需要标准引用格式

Dimension 5: 后续动作 (Next Step)
  "我要写报告" → 需要可引用的来源
  "我要复现" → 需要代码+详细参数
  "我要评估" → 需要 benchmark 数据
```

#### 典型错误拆解
```
【案例 1】
用户: "找一下 Attention is All You Need"
✗ AI 错误理解: "找" = "阅读全文"
   行动: 自动读取 HTML 版全文，输出 2 万字内容
   问题: 用户只是要确认论文存在，或要链接引用

✓ AI 正确理解: "找" = "定位"
   行动: wr academic "Attention is All You Need"
   输出: 标题、作者、年份、三个链接（abs/pdf/html）
   让用户决定: "需要我阅读全文并总结吗？"

【案例 2】
用户: "分析一下 Transformer 的创新点"
✗ AI 错误理解: 看摘要就能分析
   行动: 访问 abs 页，基于摘要输出分析
   问题: 摘要不会描述创新点的细节

✓ AI 正确理解: "分析创新点"需要理解全文
   行动: 
     1. 访问 html/1706.03762 获取全文
     2. 仔细阅读 Introduction + Method + Conclusion
     3. 总结创新点（相对于之前的方法）

【案例 3】
用户: "对比 BERT 和 GPT 的区别"
✗ AI 错误理解: 一次搜索完成
   行动: wr do "对比 BERT 和 GPT"
   问题: AI 自己知识可能有偏差，需要基于真实论文

✓ AI 正确理解: 需要分别获取两篇论文的信息
   行动:
     1. wr academic "BERT Pre-training" → 获取 BERT 论文信息
     2. wr academic "GPT Improving Language Understanding" → 获取 GPT 论文信息
     3. 分别阅读两篇论文的关键章节
     4. 基于论文内容做对比分析（而非基于记忆）

【案例 4】（典型错误：啰嗦描述 + 误解 do）
用户: "获取小红书笔记 https://xhs.link/abc 的标题、正文和评论"
✗ AI 错误行为:
   行动: wr do "获取小红书笔记 https://xhs.link/abc 的标题、正文和评论内容"
   问题:
     1. 任务描述冗长啰嗦（重复描述要获取的内容）
     2. 没有理解 do 的 completion_contract 机制
     3. 没有先检查是否需要登录（wr auth-hint）

✓ AI 正确做法（理解 do 的简洁版）:
   wr do "小红书帖子 https://xhs.link/abc"
   
   为什么这么简洁可以？
   - do 的 planner 会自动识别这是小红书链接
   - 自动选择 xiaohongshu_detail 策略
   - 该策略内置 completion_contract: ["body", "author", "engagement", "comments"]
   - 不需要在任务描述中重复这些字段！

✓ AI 正确做法（直接控制版）:
   如果明确知道要获取什么，且不需要 do 的智能处理：
   wr html https://xhs.link/abc --js
   
   区别：
   - wr html: 直接获取 HTML，自己解析
   - wr do: 智能分析 + 使用专用 reader + 完成度检查
```

#### 🚨 do 的正确使用哲学（重新理解）
```
【核心认知修正】
do 不是"多步骤编排工具"，而是"智能任务执行引擎"

do 的本质价值:
  1. 【意图解析】从自然语言提取关键信息（URL/平台/意图）
  2. 【策略选择】自动选择最佳处理方式（8种策略按优先级匹配）
     - XiaohongshuDetailStrategy (priority=120)
     - BilibiliDetailStrategy (priority=110)
     - SocialDetailStrategy (priority=100)
     - SocialSearchStrategy (priority=80)
     - AcademicStrategy (priority=70)
     - CommerceStrategy (priority=60)
     - UrlStrategy (priority=50)
     - GeneralResearchStrategy (priority=10)
  3. 【内置最佳实践】每个策略内置该场景的最佳流程
     - 如：小红书策略会自动检查 auth → 使用专用 reader → 提取评论
  4. 【完成度保证】通过 completion_contract 确保数据完整性
     - 检查是否拿到 body/author/comments 等
  5. 【错误恢复】内置 fallback_chain，失败时自动降级

【何时应该用 do？】

✓ 强烈推荐使用 do 的场景:
  
  1. 有具体 URL 的平台内容获取
     例: wr do "https://xhs.link/abc"
     理由: 
       - 自动识别是 "xiaohongshu_detail"
       - 自动检查 auth-hint
       - 自动使用 xiaohongshu_reader（处理反爬、登录态）
       - 自动检查是否拿到 comments
     对比 wr html:
       - wr html 不会自动检查登录态
       - wr html 不会自动使用专用 reader
       - wr html 不会检查完成度
  
  2. 复杂的自然语言任务
     例: wr do "分析这篇论文的创新点"
     理由:
       - 自动识别是学术任务
       - 自动规划：获取全文→定位Intro→提取创新点
       - 自动选择 academic 策略
  
  3. 需要确保数据完整性的任务
     例: wr do "小红书帖子 https://... 及评论" --strict
     理由:
       - strict 模式会检查 completion
       - 如果 comments 没拿到，会标记为 partial
       - 不会误导用户说"完成了"其实没拿到数据

✗ 不需要用 do 的场景:
  
  1. 简单的、明确的、一次性的页面获取
     例: "看下这个网页 https://example.com"
     用: wr html https://example.com
     理由: 直接、简单、不需要智能分析
  
  2. 已经明确知道最佳工具的批量搜索
     例: "搜索 RAG 论文"
     用: wr academic "RAG"
     理由: 直接调用学术搜索，比 do 的规划更快

【选择决策树】
```
有具体 URL？
  ├─ 是 → 是社交平台（小红书/B站/知乎）？
  │       ├─ 是 → 用 do（自动处理认证、专用 reader、完成检查）
  │       └─ 否 → 用 wr html（简单直接）
  └─ 否 → 是学术/电商/社交搜索？
          ├─ 是 → 用专用工具（academic/shopping/social）
          └─ 否 → 用 do（自动规划）
```

【关键区别】
  wr do "https://xhs.link/abc"
    → 智能分析 → xiaohongshu_detail 策略 → 专用 reader → 完成检查
    → 适合：需要确保拿到完整数据（特别是评论）
  
  wr html https://xhs.link/abc --js
    → 直接获取 HTML
    → 适合：简单快速获取，自己解析
```

#### 执行前必问清单
```
在决定使用什么 WR 命令前，先回答:

□ 是否有具体 URL？
   ├─ 是 → 是社交平台（小红书/B站/知乎/微博）？
   │       ├─ 是 → 用 do（自动处理认证、专用 reader、完成检查）
   │       └─ 否 → 用 wr html（简单直接）
   └─ 否 → 是学术/电商/社交搜索？
           ├─ 是 → 用专用工具（academic/shopping/social）
           └─ 否 → 用 do（自动规划）

□ 是否需要确保数据完整性？（特别是评论区）
   → 是 → 用 do --strict（有 completion 检查）

□ 是否是不确定的复杂任务？（不知道最佳处理方式）
   → 是 → 用 do（让 planner 自动选择策略）

□ 是否已明确知道最佳工具？
   → 是 → 直接用该工具（跳过 do 的规划开销）

如果任何一项不确定 → 先用 wr skills --resolve 查看推荐策略
```

### 原则 7: 学术文献访问的意图分层
**违反此原则的 AI 行为**: 分不清"找论文"和"读论文"的区别，不会选择正确的 arXiv 格式
**正确认知**:
```
任务意图分层:

Level 1: 查找/定位论文 (Bibliographic)
  用户需求: "找到某篇论文" "这篇论文存在吗" "论文的基本信息"
  正确做法: 
    - 使用 wr academic 返回元数据（标题、作者、摘要、链接）
    - 不需要访问全文，返回链接即可
    - 用户自己决定是否深入阅读

Level 2: 获取论文全文 (Full-text)
  用户需求: "阅读论文原文" "总结论文方法" "提取论文中的表格/数据"
  正确做法:
    - 必须访问全文内容，不能只看摘要页
    - arXiv 链接格式选择（按优先级）:
      1. HTML 实验版: https://arxiv.org/html/1706.03762 (AI 最易读取)
      2. PDF 版: https://arxiv.org/pdf/1706.03762 (结构化但需解析)
      3. 避免: https://arxiv.org/abs/1706.03762 (只有摘要，不是原文)
    - 使用: wr html <HTML版URL> --max-chars=200000

关键区分:
  "找论文" → 返回元数据 + 链接
  "读论文" → 必须获取全文内容（HTML 版优先）

arXiv URL 模式识别:
  abs/1706.03762    → 摘要页（只有标题、作者、摘要）
  pdf/1706.03762    → PDF 原文（适合下载，AI 读取需解析）
  html/1706.03762   → HTML 原文（AI 最友好，可直接阅读）

错误示例:
  用户: "阅读 Transformer 论文原文"
  ✗ AI: 访问 abs 页，返回摘要，说"这是论文信息"
  ✓ AI: 识别出需要全文，访问 html/ 版，返回完整内容

正确示例:
  用户: "找到 Transformer 论文"
  ✓ AI: 使用 wr academic "Attention is All You Need"，返回元数据+三个链接
     让用户自己选择要看哪个版本

【语义关键词速查】
用户用词          意图层级    是否需要全文    WR 策略
─────────────────────────────────────────────────────────
找/查/搜索        Level 1     否             wr academic，返回链接
读/看/了解        Level 1-2   视情况而定     先确认深度，再决定是否读全文
分析/总结/提取    Level 2     必须           wr html <html版URL>
对比/比较         Level 2+    必须多源       分别获取每篇全文
获取/爬/抓        Level 1-2   视数据而定     明确数据粒度后执行
引用/参考         Level 1     否             wr academic，获取标准引用格式
```

### 原则 8: 强化记忆 - 不要忘记 wr cookie
**违反此原则的 AI 行为**: 遇到平台任务直接执行，失败后才发现需要登录
**正确认知**:
```
【强制提醒】任何涉及以下平台的任务，执行前必须先检查认证：

必须检查的平台（高概率需要登录）:
  - 小红书 (xiaohongshu.com)
  - 知乎 (zhihu.com) - 部分公开内容不需要
  - 微博 (weibo.com)
  - 抖音 (douyin.com)
  - B站/哔哩哔哩 (bilibili.com)
  - Twitter/X (twitter.com, x.com)

检查流程（不可跳过）:
  1. 提取/识别目标 URL
  2. 执行: wr auth-hint <URL>
  3. 如果显示 "login_required": true 或 "需要登录"
  4. 立即执行: wr cookie <平台名>
  5. 再次执行: wr auth-hint <URL> 验证已通过
  6. 才能继续执行主任务

常见错误:
  ✗ 直接: wr html https://xiaohongshu.com/explore/xxx
  ✓ 先: wr auth-hint https://xiaohongshu.com/explore/xxx
     如果需要登录 → wr cookie xiaohongshu
     然后再: wr html https://xiaohongshu.com/explore/xxx --js

记忆口诀:
  "平台任务先 auth，提示登录就 cookie，验证通过再执行"
```

### 原则 9: 错误响应 - 第一时间 wr help / wr doctor
**违反此原则的 AI 行为**: 遇到错误盲目猜测、乱试参数、凭记忆瞎编
**正确认知**:
```
【错误处理铁律】

遇到任何 WR 相关错误时，第一反应必须是：

Step 1: 执行 wr help
  - 确认命令拼写正确
  - 查看该命令的正确用法
  - 检查是否有遗漏的必要参数

Step 2: 执行 wr doctor
  - 检查环境是否就绪
  - 检查依赖是否完整
  - 检查 AI skills 是否正确安装

Step 3: 如果仍有问题
  - 查看 SKILL.md（本文件）
  - 查看 TROUBLESHOOTING.md
  - 按照故障诊断流程排查

禁止行为:
  ✗ "这个错误可能是...，让我试试..."（猜测）
  ✗ "我记得这个命令应该..."（凭记忆）
  ✗ "参数不对的话我换个..."（乱试）

正确行为:
  ✓ "遇到错误，先执行 wr help 确认用法"
  ✓ "wr doctor 检查环境"
  ✓ "按照文档排查"

常见需要查 help 的场景:
  - 命令返回 "unknown command"
  - 参数不被识别
  - 不确定某个功能用什么命令
  - 忘记了参数格式

记忆口诀:
  "遇事不决先 help，环境疑问用 doctor，不要乱猜看文档"
```

## 深度理解：wr do 的正确使用方式

### 为什么 do 依赖输入质量？
```
do 的工作原理:
  用户输入 → TaskSpec → Strategy Selection → Workflow Generation → Execution

如果输入模糊:
  "分析一下小红书" 
  → TaskSpec 不明确（分析什么？哪个帖子？多深？）
  → Strategy 可能选错
  → Workflow 生成不正确
  → 结果不符合预期

如果输入清晰:
  "分析小红书帖子 https://xhs.link/xxx 的正文内容和前20条评论情绪"
  → TaskSpec 明确（URL、平台、内容、数量）
  → Strategy 正确选择 xiaohongshu_detail
  → Workflow 生成精准的抓取步骤
  → 结果符合预期
```

### do 的事先拆解框架
```
使用 do 前，必须先完成以下拆解：

【拆解清单】

□ Step 1: 明确目标实体
   - 具体 URL 还是搜索关键词？
   - 如果是搜索，范围是什么？（平台？时间？数量？）
   
□ Step 2: 明确操作动作
   - 获取原始数据？
   - 提取特定信息？
   - 分析总结？
   - 对比多个实体？

□ Step 3: 明确输出要求
   - 需要引用吗？
   - 需要特定格式吗？（表格/列表/段落）
   - 需要多详细？（摘要/详细/全文）

□ Step 4: 识别潜在障碍
   - 需要登录吗？（wr auth-hint 检查）
   - 有反爬吗？（需要 --js？）
   - 数据量大吗？（需要分批？）

□ Step 5: 验证可执行性
   - 用 wr skills --resolve 验证理解是否正确
   - 用 wr do-plan 查看生成的计划是否合理
   - 确认无误后再 wr do --strict
```

### do 的输入优化示例
```
【核心原则】简洁明确 > 冗长详细

【案例 1：模糊输入】
❌ 差: "爬一下小红书"
   问题: 爬什么？哪个帖子？什么数据？多少条？
   结果: do planner 会迷茫，可能生成不合适的 workflow

✅ 优: "获取小红书帖子 https://xhs.link/abc 的正文和前10条评论"
   明确要素:
     - 平台: 小红书
     - 目标: 具体 URL
     - 内容: 正文 + 评论
     - 数量: 评论前10条
   结果: planner 能精准生成 workflow

【案例 2：学术任务】
❌ 差: "研究一下 BERT"
   问题: 研究什么方面？论文？应用？对比？

✅ 优: "总结 BERT 论文的核心创新点，对比传统语言模型"
   明确要素:
     - 任务: 总结创新点
     - 目标: BERT 论文
     - 对比对象: 传统语言模型

【案例 3：多步骤任务】
❌ 差: "分析电商平台上 iPhone 的评价"
   问题: 哪个平台？哪些评价？分析什么维度？

✅ 优: "搜索 iPhone 15 评价，获取淘宝京东各50条，分析优缺点频率"
   明确要素:
     - 商品: iPhone 15
     - 平台: 淘宝 + 京东
     - 数据: 各50条评价
     - 分析: 优缺点频率

【案例 4：典型的啰嗦输入（禁止）】
❌ 极差（写小作文）:
   "请帮我获取小红书笔记 https://www.xiaohongshu.com/explore/abc123 
    的所有信息，包括标题、正文、图片、评论内容，
    要完整准确，谢谢！"
   
   问题:
     1. 给了具体 URL 却用 do（应该用 wr html）
     2. 描述太啰嗦，关键信息淹没在礼貌用语中
     3. 没有检查 auth-hint
     4. "完整准确" 这类词对 planner 没有实际意义

✅ 正确做法（如果非要用 do）:
   wr do "分析小红书帖子 https://xhs.link/abc123 的内容和评论"
   
   更好的做法（直接 html）:
   wr html https://xhs.link/abc123 --js

【输入简洁性检查清单】
□ 是否包含 URL？→ 考虑直接用 wr html
□ 是否超过 20 个字？→ 尝试精简到核心动词+对象
□ 是否有礼貌用语？→ 删除（"请帮我""谢谢"等）
□ 是否有主观描述？→ 删除（"完整准确""详细"等）
□ 关键信息（URL/平台/数量）是否清晰？→ 放在最前面
```

### do 的三层质量检查
```
在使用 do 前，必须通过三层检查：

Layer 1: 清晰度检查
  问: 一个陌生人看了我的任务描述，能明确知道要做什么吗？
  如果否 → 补充具体信息（URL、数量、平台、格式）

Layer 2: 可行性检查
  问: 这个任务技术上可行吗？WR 有能力做到吗？
  如果否 → 拆解成多个小任务，或换用其他工具

Layer 3: 完整性检查
  问: 我是否遗漏了关键约束？（认证、反爬、输出格式）
  如果可能遗漏 → 用 wr do-plan 预览，看生成的步骤是否完整
```

### 何时不该用 do？
```
【反模式】滥用 do

不该用 do 的场景:
  ✗ 简单单页访问 → 用 wr html <url>
  ✗ 纯学术搜索 → 用 wr academic
  ✗ 纯社交搜索 → 用 wr social
  ✗ 纯电商搜索 → 用 wr shopping
  ✗ 已知具体 URL 的平台详情页 → 先 wr auth-hint → wr cookie → wr html

该用 do 的场景:
  ✓ 多步骤组合（搜索+抓取+分析）
  ✓ 需要跨平台对比
  ✓ 需要特定格式的结构化输出
  ✓ 复杂的条件逻辑（如果A失败则尝试B）
  ✓ 需要引用和来源追踪的完整报告

【判断标准】
如果任务可以用一个简单命令完成 → 不要用 do
如果任务需要多个步骤组合 → 考虑用 do
如果不确定 → 先用 wr skills --resolve 查看推荐
```

## 任务类型决策树

### 决策节点 1: 是否涉及详情页？
```
用户提供的是具体 URL?
  ├─ 是 → 决策节点 2
  └─ 否 → 决策节点 3
```

### 决策节点 2: 什么类型的详情页？
```
URL 域名识别:
  ├─ xiaohongshu.com / xhslink.com
  │   ├─ 先执行: wr auth-hint <url>
  │   ├─ 如果提示需要登录: wr cookie xiaohongshu
  │   └─ 然后: wr html <url> --js (自动走专用 reader)
  │       或: wr do "分析该小红书帖子" (让 planner 决定)
  │
  ├─ bilibili.com / b23.tv
  │   ├─ 先执行: wr auth-hint <url>
  │   ├─ 如果需要评论区: wr html <url> --js
  │   └─ 或: wr do "分析该 B站视频及评论"
  │
  ├─ zhihu.com
  │   ├─ 如果回答/文章: wr html <url> --js
  │   └─ 如果话题/搜索: wr social "话题" --platform=zhihu
  │
  ├─ weibo.com
  │   ├─ 大概率需要登录: wr cookie weibo
  │   └─ wr html <url> --js
  │
  └─ 其他通用网站
      └─ wr html <url> [--js] [--max-chars=100000]
```

### 决策节点 3: 什么类型的搜索？
```
任务关键词识别:

  ├─ 包含 "论文" "文献" "arxiv" "citation" "benchmark"
  │   └─ 使用: wr academic "<query>" [--source=arxiv,google_scholar,...]
  │       进阶: wr do --skill=academic_relation_mining
  │
  ├─ 包含 "小红书" "知乎" "微博" "抖音" "B站" "评论" "舆情"
  │   └─ 使用: wr social "<query>" [--platform=xxx]
  │       进阶: wr do --skill=social_comment_mining
  │
  ├─ 包含 "淘宝" "京东" "拼多多" "价格" "评价" "比价"
  │   └─ 使用: wr shopping "<query>" [--platform=xxx]
  │       进阶: wr do --skill=commerce_review_mining
  │
  ├─ 包含 "GitHub" "StackOverflow" "技术" "代码"
  │   └─ 使用: wr tech "<query>" [--source=xxx]
  │
  ├─ 需要深度研究/多源对比/交叉验证
  │   ├─ 使用: wr deep "<query>" [--variants=4] [--crawl=5]
  │   └─ 或: wr mindsearch "<query>" [--turns=3] [--branches=4]
  │
  └─ 通用搜索
      ├─ 快速: wr quick "<query>"
      ├─ 标准: wr web "<query>" [--crawl-pages=5]
      └─ 复杂: wr do "<复杂多步骤任务>"
```

## 认证与 Cookie 管理

### 认知: Cookie 是状态，不是配置
**关键理解**: Cookie 会过期，过期后需要更新。AI 必须具备"Cookie 可能过期"的认知。

### 标准认证流程
```
任何可能涉及登录态的任务开始前:

Step 1: 检测认证需求
  wr auth-hint <目标URL>

  输出分析:
    - "需要登录" / "login_required": true → 进入 Step 2
    - "挑战页检测" / "challenge_detected": true → 进入 Step 3
    - "可直接访问" → 继续任务

Step 2: 更新 Cookie
  wr cookie <平台> [--browser=safari|chrome|edge]

  平台识别:
    - xiaohongshu: 从小红书网页版获取 cookie
    - zhihu: 从知乎获取 cookie
    - bilibili: 从 B站获取 cookie
    - weibo: 从微博获取 cookie
    - douyin: 从抖音获取 cookie

  执行后会生成/更新 .web-rooter/login_profiles.json

Step 3: 处理挑战页 (Challenge)
  wr challenge-profiles
  → 查看支持的挑战类型

  WR 会自动处理大多数 Cloudflare/Turnstile，但如果持续失败:
  - 检查浏览器是否可见 (--no-headless 调试用)
  - 可能需要手动通过一次验证后保存 cookie

Step 4: 验证认证成功
  再次执行 wr auth-hint <目标URL>
  确认 "需要登录": false
```

### Cookie 失效诊断
```
爬取失败症状 → 诊断 → 解决方案:

症状: 403 Forbidden / "需要登录" / 页面内容只有登录框
诊断:
  wr auth-hint <失败的URL>
  wr cookie (不带参数查看现有配置)
解决方案:
  wr cookie <平台> --browser=xxx (重新获取)
  然后重试原任务

症状: 460 Verification Required / captcha
诊断:
  wr challenge-profiles
  wr context --event=challenge_failure
解决方案:
  - 降低请求频率 (添加 --command-timeout-sec=120)
  - 使用浏览器模式 (--js)
  - 或者手动通过验证后更新 cookie
```

## 参数工程指南

### 参数传递的认知模型
**错误认知**: "参数越多越好" 或 "我不确定就不传"
**正确认知**: "每个参数都有特定场景，我需要判断当前场景是否需要"

### 核心参数决策矩阵

#### `--js` (使用浏览器)
```
何时需要:
  ✓ 页面内容是 JS 动态渲染 (React/Vue/Angular 现代网站)
  ✓ 需要获取评论区 (大部分社交平台)
  ✓ 遇到 anti-bot 挑战 (Cloudflare 等)
  ✓ 页面返回 200 但内容为空

何时不需要:
  ✗ 纯静态 HTML 页面
  ✗ 只需要获取文章正文 (新闻网站)
  ✗ 追求速度优先的简单任务

检测方法:
  wr html <url> (不用 --js)
  如果返回内容明显不完整 → 加 --js 重试
```

#### `--max-chars`
```
默认值: 80000
调大场景:
  - 需要完整文章: 150000
  - 需要多页文档: 250000

调小场景 (内存压力时):
  - 只需要摘要: 30000
  - 只需要链接列表: 10000
```

#### `--top` / `--num-results`
```
默认值: 5-8
调大场景:
  - 需要全面覆盖: 15-20
  - 学术研究: 10-15

调小场景:
  - 快速验证: 3-5
  - 只需要最相关结果: 3
```

#### `--crawl-pages` / `--crawl`
```
含义: 搜索结果中需要实际访问并抓取的页面数

决策:
  只需要摘要 → 0 或不用
  需要正文 → 3-5
  深度研究 → 8-10

注意: 每多爬一页就增加失败概率和耗时，按需设置
```

#### `--strict`
```
含义: 启用完成契约检查，如果 required_outputs 不满足会标记失败

何时使用:
  ✓ 生产环境任务
  ✓ 需要确保数据完整性的场景
  ✓ 社交评论挖掘 (必须拿到 comments)

何时不用:
  ✗ 探索性任务
  ✗ 快速原型
  ✗ 知道可能会有部分缺失的场景
```

#### `--timeout-sec`
```
场景:
  - 长文章/视频页面: 60-120
  - 复杂反爬页面: 90-180
  - 简单页面: 30 (默认)
```

### 复杂参数传递示例

```bash
# 错误的参数传递 (AI 常犯的错误)
wr do "分析小红书 iPhone 评论" --js --max-chars=200000 --top=20 --crawl-pages=10 --strict --timeout-sec=300

# 问题分析:
# 1. wr do 不需要 --js (do 内部会根据策略决定)
# 2. --max-chars 对 do 不直接生效
# 3. --top 应该用 --top-results 或在 goal 中指定

# 正确的做法:
# 方式 1: 使用专用工具
wr social "iPhone 评测" --platform=xiaohongshu --top=10

# 方式 2: 使用 do-plan 查看推荐参数
wr do-plan "分析小红书 iPhone 评论，获取前 10 条热门帖子的标题和评论观点"
# 然后查看 playbook 中的 recommended_options

# 方式 3: 通过 skill 变量传递
wr do "分析小红书 iPhone 评论" --skill=social_comment_mining
# 在 skill 的 default_options 中已经配置了合理的参数
```

## 故障诊断与恢复手册

### Level 1: 环境诊断
```
症状: 任何异常
命令: wr doctor

输出解读:
  [OK] 全部通过 → 环境正常，问题在其他层面
  [WARN] 浏览器未安装 → 需要 playwright install chromium
  [FAIL] 依赖缺失 → 安装 requirements.txt
  [FAIL] AI Skills 未发现 → 执行 wr skills-install
```

### Level 2: 执行诊断
```
症状: 任务执行失败或不完整
命令: wr context --limit=30

查看:
  - event_type: workflow_trace → 查看执行步骤
  - event_type: fetch_failure → 查看失败 URL
  - event_type: challenge_failure → 查看反爬触发
  - event_type: auth_failure → 查看认证失败

分析:
  哪个 step 失败? → 针对性处理
  是否 soft_failed? → 可以 --continue-on-error 或调整参数
```

### Level 3: 任务诊断
```
症状: 返回成功但内容不对/不完整
命令: 检查返回结果中的 completion 字段

分析 completion_contract:
  status: "partial" → 部分成功
    missing_outputs: ["comments"] → 没拿到评论
      → 需要 --js 或更新 cookie

  status: "incomplete" → 基本失败
    → 重新设计任务或更换策略

  gate_failures: ["browser_required"] → 需要用浏览器但没用到
    → 添加相关参数或调整 skill
```

### 常见故障模式与修复

#### 模式 1: "页面打开成功但内容是登录框"
```
诊断:
  wr auth-hint <url> → 确认需要登录
修复:
  wr cookie <平台>
  重试
```

#### 模式 2: "拿到正文但没拿到评论"
```
诊断:
  completion.missing_outputs 包含 "comments"
修复:
  如果是社交平台详情页 → 使用 --js 参数
  或者 → 使用专用 reader: wr html <url> --js
```

#### 模式 3: "搜索结果为空或明显不对"
```
诊断:
  检查 query 是否过于复杂
  wr skills --resolve "<query>" → 查看推荐的引擎
修复:
  简化 query
  使用专用搜索: wr academic/wr social/wr shopping
  使用 deep: wr deep "<query>" --variants=3
```

#### 模式 4: "执行超时"
```
诊断:
  任务是否涉及大量页面?
  是否有复杂反爬?
修复:
  缩短任务范围 (减少 --crawl-pages)
  增加超时: --command-timeout-sec=180
  使用后台任务: wr do-submit → wr job-status
```

#### 模式 5: "任务执行成功但引用格式不对"
```
诊断:
  检查返回数据中的 citations 字段
修复:
  确保任务描述中包含"并给出处"或"带引用"
  使用 --strict 确保输出完整性
```

## 复杂任务拆解模式

### 模式 A: 多平台对比分析
```
任务: "对比小红书、知乎、微博上关于 X 的舆情"

错误做法:
  wr do "对比小红书知乎微博关于 X 的舆情"

正确拆解:
  Step 1: 分别获取各平台数据
    wr social "X" --platform=xiaohongshu --top=10 → 保存结果
    wr social "X" --platform=zhihu --top=10 → 保存结果
    wr social "X" --platform=weibo --top=10 → 保存结果

  Step 2: 分析各平台特点
    (AI 基于返回数据进行分析)

  Step 3: 交叉验证
    wr deep "X 舆情分析" --platforms --crawl=3

  Step 4: 综合对比
    (AI 整合所有数据生成对比报告)
```

### 模式 B: 深度研究链
```
任务: "研究 RAG 技术的最新进展"

错误做法:
  wr do "研究 RAG 技术最新进展"

正确拆解:
  Step 1: 学术基础
    wr academic "RAG retrieval augmented generation" --papers-only --source=arxiv
    → 获取核心论文

  Step 2: 技术社区讨论
    wr tech "RAG best practices 2024 2025" --source=github,stackoverflow
    → 获取工程实践

  Step 3: 深度研究
    wr mindsearch "RAG technology trends and challenges" --turns=2 --branches=3
    → 构建知识图谱

  Step 4: 验证与补充
    wr deep "RAG evaluation benchmarks" --variants=3 --crawl=5
    → 交叉验证
```

### 模式 C: 认证依赖链
```
任务: "获取我的小红书收藏夹内容"

错误做法:
  wr do "获取我的小红书收藏夹"

正确拆解:
  Step 1: 诊断认证
    wr auth-hint https://www.xiaohongshu.com/user/me
    → 确认需要个人登录态

  Step 2: 获取认证
    wr cookie xiaohongshu --browser=safari
    → 使用已登录的浏览器获取 cookie

  Step 3: 验证认证
    wr auth-hint https://www.xiaohongshu.com/user/me
    → 确认已通过

  Step 4: 执行获取
    wr html https://www.xiaohongshu.com/user/me --js
    → 或使用 do 执行更复杂的逻辑
```

## 反模式警示

### 反模式 1: 万能 do 陷阱
```
✗ 所有任务都用 wr do
✓ 简单任务用专用工具，复杂任务才用 do

自检问题:
  - 我在用 do 完成一个可以用 academic/social/shopping 完成的任务吗？
  - 我的任务真的需要多步骤编排吗？
```

### 反模式 2: 参数堆砌
```
✗ wr do "任务" --js --strict --max-chars=200000 --top=20 --crawl-pages=10
✓ 先用 wr do-plan 查看推荐参数，再选择性添加

自检问题:
  - 我了解每个参数的具体含义吗？
  - 这些参数对我的任务真的必要吗？
  - 我可以通过调整任务描述来替代参数吗？
```

### 反模式 3: 诊断逃避
```
✗ "失败了，我换一种方式试试"
✓ "失败了，我先诊断原因"

自检问题:
  - 我执行 wr doctor 了吗？
  - 我查看 wr context 了吗？
  - 我分析 completion 结果了吗？
```

### 反模式 4: 认证忽视
```
✗ 直接爬取社交平台，失败后才知道要登录
✓ 任何平台任务前先检查 auth-hint

自检问题:
  - 这个 URL/平台需要认证吗？
  - 我的 cookie 是最新的吗？
  - 我检查过 auth-hint 的提示吗？
```

## 执行检查清单

在每次执行 WR 任务前，强制回答以下问题：

```
□ 我执行过 wr doctor 了吗？（环境检查）
□ 我识别了正确的任务类型吗？（学术/社交/电商/通用）
□ 如果是平台任务，我检查过 auth-hint 吗？（认证检查）
□ 我选择了合适的工具吗？（专用工具 vs do）
□ 我的任务描述清晰吗？（包含关键信息：平台、数量、输出要求）
□ 如果是复杂任务，我分阶段执行了吗？（resolve → plan → dry-run → execute）
□ 我预估了可能的失败点吗？（认证/反爬/超时）
□ 失败后我有诊断计划吗？（doctor → auth-hint → context）
```

## 渐进式掌握路径

### 阶段 1: 基础工具使用（1-2 轮实践）
掌握:
  - wr doctor
  - wr help
  - wr visit / wr html
  - wr quick / wr web

### 阶段 2: 垂直领域工具（3-5 轮实践）
掌握:
  - wr academic
  - wr social + wr auth-hint + wr cookie
  - wr shopping
  - wr deep

### 阶段 3: 高级编排（5-10 轮实践）
掌握:
  - wr skills --resolve
  - wr do-plan
  - wr do --dry-run
  - wr do --strict

### 阶段 4: 故障诊断专家（持续）
掌握:
  - wr context 分析
  - completion contract 解读
  - 复杂任务拆解
  - 多工具链组合

---

**记住**: Web-Rooter 不是"一个工具"，而是"一套编排系统"。你的目标不是记住所有命令，而是培养"先诊断、再拆解、选专用、渐进执行、失败即查"的认知习惯。

## Repo
- Root: `{repo_text}`
- Primary docs: `README.md`, `README.zh-CN.md`, `docs/guide/CLI.md`
- Troubleshooting: 参见 TROUBLESHOOTING.md（同目录）
"""


def _cursor_rule(skill_md: str) -> str:
    return f"""
---
description: Web-Rooter 认知驱动使用规则 - 强制诊断优先、渐进式执行、专用工具优先
globs: []
alwaysApply: true
---

# Web-Rooter CLI 认知框架

## ⚠️ 核心要点速查（使用 WR 前必看）

### 🚨 绝对不能忘的三件事
1. **环境检查**：任何任务前 → `wr doctor`
2. **认证检查**：平台任务前 → `wr auth-hint <URL>` → 如需登录 → `wr cookie <平台>`
3. **错误处理**：遇到问题时 → `wr help <命令>` 或 `wr doctor`

### 🎯 工具选择速查表
| 任务类型 | 正确命令 | 禁用 |
|---------|---------|------|
| 学术文献搜索 | `wr academic "query"` | `wr do "搜索论文"` |
| 社交平台搜索 | `wr social "query" --platform=xxx` | `wr do "小红书..."` |
| 电商平台搜索 | `wr shopping "query"` | `wr do "淘宝..."` |
| 技术社区搜索 | `wr tech "query"` | `wr do "GitHub..."` |
| 简单网页获取 | `wr html <URL> [--js]` | `wr do "访问..."` |
| 深度多源研究 | `wr deep "query"` | `wr do "深度研究..."` |
| 平台详情页+完整性 | `wr do "<URL>"` | 不要使用冗长描述 |

### ⚡ 关键概念：wr do 的输入质量
**核心认知**：do 的输出质量 100% 依赖输入质量

- ❌ 模糊输入: `"分析一下小红书"` → planner 迷茫 → 失败
- ✅ 清晰输入: `"分析小红书帖子 https://xhs.link/abc 的正文和前10条评论"` → planner 精准 → 成功

**使用 do 前必须完成**：
- [ ] 明确具体 URL 或搜索范围
- [ ] 明确要获取什么数据
- [ ] 明确数量限制
- [ ] 明确输出格式
- [ ] 检查认证（wr auth-hint）
- [ ] 先用 wr do-plan 验证理解是否正确

## 执行前强制检查

### 1. 环境检查（必须）
```
任何 WR 任务执行前 → 必须运行 wr doctor
长时间未使用 WR 后 → 必须运行 wr doctor
遇到任何异常后 → 必须运行 wr doctor
```

### 2. 任务类型识别
识别到以下关键词时，使用专用工具而非 `wr do`:
- 学术相关(论文/arxiv/citation) → `wr academic`
- 社交平台(小红书/知乎/微博/B站) → `wr social`
- 电商平台(淘宝/京东/拼多多) → `wr shopping`
- 技术社区(GitHub/StackOverflow) → `wr tech`
- 深度研究/多源对比 → `wr deep` 或 `wr mindsearch`

### 3. 认证检查（平台任务）
执行社交平台任务前:
```bash
wr auth-hint <目标URL>
# 如果需要登录 → 先执行 wr cookie <平台>
# 再次 auth-hint 确认通过后再执行主任务
```

## 渐进式执行规则

### 复杂任务必须分阶段
```bash
# Stage 1: 理解任务方式
wr skills --resolve "<任务>" --compact

# Stage 2: 查看执行计划
wr do-plan "<任务>"

# Stage 3: 验证编译
wr do "<任务>" --dry-run

# Stage 4: 正式执行
wr do "<任务>" --strict
```

### 禁止行为
- ✗ 所有任务都用 `wr do`
- ✗ 直接 `wr do "任务" --strict` 跳过前面阶段
- ✗ 失败后"换一种方式试试"而不诊断
- ✗ 忽视 `auth-hint` 的提示
- ✗ **写小作文式任务描述（冗长重复）**

### 输入简洁性原则
```
❌ 冗长: "获取小红书笔记 https://... 的所有信息，包括标题、正文..."
   问题：描述重复，do 的 completion contract 已定义要获取什么

✅ 简洁: wr do "https://xhs.link/abc"
   策略会自动：识别平台 → 检查认证 → 使用专用 reader → 完成检查

✅ 带上下文: wr do "分析这篇小红书 https://xhs.link/abc 的核心观点"
   明确分析意图，但不重复描述要获取什么（因为 reader 会获取）
```

### 🚨 do 的正确使用哲学
```
【核心认知】do 不是"多步骤编排工具"，而是"智能任务执行引擎"

do 的本质价值:
  1. 【意图解析】从自然语言提取关键信息
  2. 【策略选择】自动选择最佳处理方式（8种策略）
  3. 【内置最佳实践】自动处理认证、使用专用 reader
  4. 【完成度保证】通过 completion_contract 确保数据完整性
  5. 【错误恢复】内置 fallback_chain

【何时用 do？】
  ✓ 有具体 URL 的平台内容（小红书/B站等）
    → 自动识别平台、检查认证、使用专用 reader、完成检查
  ✓ 复杂的自然语言任务
    → 自动规划执行步骤
  ✓ 需要确保数据完整性
    → 用 do --strict，有 completion 检查

【何时不用 do？】
  ✗ 简单的、明确的一次性页面获取
    → 直接用 wr html
  ✗ 已明确知道最佳工具的批量搜索
    → 直接用 wr academic/social/shopping

【典型错误】
  ❌ wr do "获取小红书笔记 https://xhs.link/abc 的标题、正文和评论内容"
     问题: 描述冗长，重复要获取的内容（do 的 completion_contract 已定义）
  
  ✅ wr do "小红书帖子 https://xhs.link/abc"
     简洁，让 planner 自动处理
  
  ✅ wr do "https://xhs.link/abc"
     更简洁，URL 已足够
```

## 故障诊断流程

### 任何失败后必须执行
```bash
# 1. 环境诊断
wr doctor

# 2. 认证诊断（如果是平台任务）
wr auth-hint <失败的URL>

# 3. 执行痕迹诊断
wr context --limit=20

# 4. 分析 completion 结果（检查 missing_outputs 和 gate_failures）
```

### 常见症状与修复
| 症状 | 诊断命令 | 修复方案 |
|-----|---------|---------|
| 403/需要登录 | `wr auth-hint` | `wr cookie <平台>` |
| 内容为空 | `wr html <url>` vs `wr html <url> --js` | 加 `--js` 参数 |
| 只有正文无评论 | 检查 completion | 使用 `--js` 或专用 reader |
| 超时 | 检查任务复杂度 | 减少 `--crawl-pages` 或增加 `--command-timeout-sec` |
| 结果不匹配 | `wr skills --resolve` | 使用专用工具或调整 query |

## 参数使用原则

### 避免参数堆砌
✗ `wr do "任务" --js --strict --max-chars=200000 --top=20 --crawl-pages=10`
✓ 先用 `wr do-plan` 查看推荐参数

### 关键参数含义
- `--js`: JS 渲染页面/评论区/反爬挑战
- `--strict`: 启用完成契约检查（生产环境用）
- `--crawl-pages=N`: 搜索结果中实际爬取的页面数
- `--top=N`: 搜索结果数量
- `--command-timeout-sec=N`: 单命令超时时间

## 专用工具优先

### 学术搜索
```bash
# ✗ 错误
wr do "搜索 RAG 论文"

# ✓ 正确
wr academic "RAG" --papers-only --source=arxiv,google_scholar
```

### 社交搜索
```bash
# ✗ 错误
wr do "小红书 iPhone 评测"

# ✓ 正确
wr social "iPhone 评测" --platform=xiaohongshu,zhihu
```

### 电商搜索
```bash
# ✗ 错误
wr do "淘宝 iPhone 价格"

# ✓ 正确
wr shopping "iPhone" --platform=taobao,jd
```

## Cookie 管理

### 平台任务标准流程
```bash
# 1. 检测
wr auth-hint <url>

# 2. 获取（如需要）
wr cookie xiaohongshu --browser=safari

# 3. 验证
wr auth-hint <url>

# 4. 执行
wr html <url> --js
```

### Cookie 失效症状
- 页面内容只有登录框
- 403 Forbidden
- "需要登录" 提示

**修复**: `wr cookie <平台>` 重新获取

## 复杂任务拆解

### 多平台对比
✗ `wr do "对比小红书知乎微博关于 X 的舆情"`
✓
```bash
wr social "X" --platform=xiaohongshu
wr social "X" --platform=zhihu
wr social "X" --platform=weibo
# 然后 AI 整合分析
```

### 深度研究链
```bash
# 1. 学术基础
wr academic "RAG" --papers-only

# 2. 技术实践
wr tech "RAG best practices"

# 3. 深度研究
wr mindsearch "RAG trends"

# 4. 交叉验证
wr deep "RAG evaluation"
```

## 反模式检查

执行前自问:
- [ ] 我执行 `wr doctor` 了吗？
- [ ] 我在用专用工具还是滥用 `wr do`？
- [ ] 我检查 `auth-hint` 了吗？
- [ ] 我的任务描述清晰吗？
- [ ] 我分阶段执行了吗？
- [ ] 失败后有诊断计划吗？

## 关键认知

1. **WR 是编排系统，不是单一工具** - 选专用工具
2. **诊断优先于执行** - doctor/auth-hint 先行
3. **渐进式执行** - resolve → plan → dry-run → execute
4. **失败即诊断** - 不盲试，先查 context/completion
5. **Cookie 是状态** - 会过期，需要更新

---
详细文档参见: `.agents/skills/web-rooter/SKILL.md`
故障诊断参见: `.agents/skills/web-rooter/TROUBLESHOOTING.md`
"""


def _agents_md(skill_md: str) -> str:
    return f"""# Web-Rooter Agent Skill Pack

This file is managed by Web-Rooter skill installers.

{skill_md}
"""


def _troubleshooting_md() -> str:
    return """# Web-Rooter 故障诊断速查表

> 不按顺序执行这些诊断步骤就尝试修复，是对时间的浪费。

## 标准诊断流程（必须按顺序）

### Step 1: 环境诊断
```bash
wr doctor
```
**预期输出**: 全部 [OK]
**如果有 [FAIL]**: 先修复环境问题，不要继续执行其他命令

### Step 2: 任务理解诊断
```bash
wr skills --resolve "<你的任务>" --compact
```
**检查点**:
- `selected_skill` 是否符合预期？
- `route` 是否正确？
- `micro_skills` 有什么特别提示？

**如果不符合预期**: 调整任务描述，更明确地指定平台/类型

### Step 3: 认证诊断（平台任务）
```bash
wr auth-hint <目标URL>
```
**关键字段**:
- `login_required`: true → 必须执行 `wr cookie <平台>`
- `challenge_detected`: true → 可能需要浏览器模式或人工辅助
- `suggested_action`: 按照建议执行

### Step 4: 执行痕迹诊断
```bash
wr context --limit=30
```
**关注 event_type**:
- `workflow_trace`: 查看执行步骤
- `fetch_failure`: 查看失败的 URL 和原因
- `challenge_failure`: 反爬挑战失败
- `auth_failure`: 认证失败

### Step 5: 完成度诊断
检查最后一次执行返回的 `completion` 字段:
```json
{
  "status": "partial",
  "completion_percent": 75,
  "missing_outputs": ["comments"],
  "gate_failures": ["browser_required"]
}
```
**status 解读**:
- `complete`: 成功，无需进一步操作
- `partial`: 部分成功，查看 missing_outputs 和 gate_failures
- `incomplete`: 基本失败，重新设计任务

## 症状-诊断-修复对照表

### 症状 A: 403 Forbidden / Access Denied
**诊断**:
```bash
wr auth-hint <url>
wr doctor  # 检查网络
```
**可能原因**:
1. 需要登录 → `login_required: true`
2. IP 被封 → 需要代理
3. 请求头被拒绝 → 需要浏览器模式

**修复**:
```bash
# 原因 1: 登录
wr cookie <平台> --browser=safari
wr auth-hint <url>  # 验证
# 然后重试

# 原因 2: 浏览器模式
wr html <url> --js  # 代替普通访问

# 原因 3: 如果是 do 任务，确保使用 --js
wr do "<任务>" --js
```

### 症状 B: 页面打开但内容为空/只有登录框
**诊断**:
```bash
wr html <url>  # 不用 --js，看返回什么
wr auth-hint <url>
```
**可能原因**:
1. JS 动态渲染 → 需要 `--js`
2. 需要登录 → 需要 `wr cookie`

**修复**:
```bash
# 测试是否是 JS 问题
wr html <url> --js --max-chars=50000
# 如果有内容了，说明原任务需要加 --js

# 如果还是登录框
wr cookie <平台>
wr html <url> --js
```

### 症状 C: 拿到正文但没拿到评论
**诊断**:
```bash
# 查看 completion
# missing_outputs 应该包含 "comments"
```
**可能原因**:
1. 评论需要 JS 渲染
2. 评论区需要额外触发（滚动/点击）
3. 评论 API 单独调用，需要特定处理

**修复**:
```bash
# 方式 1: 使用专用 reader（推荐）
wr html <url> --js
# 小红书/Bilibili 会自动走专用 reader

# 方式 2: 使用 social skill
wr do "<任务>" --skill=social_comment_mining

# 方式 3: 如果是简单访问，确保 --js
wr html <url> --js --max-chars=100000
```

### 症状 D: 搜索结果为空或不相关
**诊断**:
```bash
wr skills --resolve "<query>"
# 检查推荐的引擎和 route
```
**可能原因**:
1. query 太复杂，搜索引擎无法解析
2. 使用了错误的搜索引擎
3. 搜索结果被过滤/个性化

**修复**:
```bash
# 方式 1: 简化 query
# ✗ "分析2024年最新RAG技术在中文领域的应用和benchmark结果"
# ✓ "RAG retrieval augmented generation 2024 benchmark"

# 方式 2: 使用专用工具
wr academic "RAG benchmark 2024"  # 学术
wr tech "RAG implementation"       # 技术
wr deep "RAG trends" --variants=3  # 深度

# 方式 3: 手动指定引擎
wr web "<query>" --engine=google,bing
```

### 症状 E: 执行超时
**诊断**:
```bash
wr context --event=workflow_trace
# 查看在哪个 step 超时
```
**可能原因**:
1. 页面加载慢（JS 重）
2. 爬取页面太多
3. 网络问题

**修复**:
```bash
# 方式 1: 增加超时
wr do "<任务>" --command-timeout-sec=180

# 方式 2: 减少爬取页面
wr web "<query>" --crawl-pages=3  # 原来是 5-10

# 方式 3: 使用后台任务
wr do-submit "<任务>" --timeout-sec=600
wr job-status <job_id>

# 方式 4: 简化任务，分步执行
# 不要一次爬太多，分批处理
```

### 症状 F: 任务返回成功但引用格式不对
**诊断**:
```bash
# 检查返回数据中的 citations 字段
# 检查 references_text 字段
```
**可能原因**:
1. 任务描述没有明确要求出处
2. 输出被截断
3. 格式解析失败

**修复**:
```bash
# 方式 1: 明确任务描述
# ✗ "搜索 RAG 论文"
# ✓ "搜索 RAG 论文并给出处，包括标题、作者、URL"

# 方式 2: 使用专用工具（自动处理引用）
wr academic "RAG"  # 自动返回 citations
wr deep "RAG"      # 自动返回 citations + comparison

# 方式 3: 使用 --strict 确保完整性
wr do "<任务>" --strict
```

### 症状 G: Cookie 疑似过期（之前能访问，现在不能）
**诊断**:
```bash
wr auth-hint <之前能访问的URL>
# 查看 login_required 是否为 true

wr cookie  # 不带参数，查看现有配置
```
**修复**:
```bash
# 更新特定平台的 cookie
wr cookie xiaohongshu --browser=safari
wr cookie zhihu --browser=chrome
# 等等

# 验证
wr auth-hint <url>
```

### 症状 H: 反爬挑战（Cloudflare/验证码）
**诊断**:
```bash
wr challenge-profiles
wr context --event=challenge_failure
```
**可能原因**:
1. 请求频率太高
2. 需要浏览器模拟
3. 需要特定 cookie

**修复**:
```bash
# 方式 1: 使用浏览器模式
wr html <url> --js
# WR 会自动尝试处理 challenge

# 方式 2: 降低频率
# 添加延迟参数（如果工具支持）

# 方式 3: 手动通过一次
# 用普通浏览器访问，通过验证后
wr cookie <平台>  # 保存带验证状态的 cookie

# 方式 4: 使用 do 的 skill 模板
# skill 中配置了浏览器优先和反爬处理
wr do "<任务>" --skill=social_comment_mining
```

## 快速决策树

```
遇到问题?
  │
  ├─→ 执行 wr doctor
  │     ├─→ 有 FAIL → 修复环境问题
  │     └─→ 全部 OK → 继续
  │
  ├─→ 是平台任务(小红书/知乎/微博/B站)?
  │     ├─→ 执行 wr auth-hint <url>
  │     │       ├─→ 需要登录 → wr cookie <平台> → 重试
  │     │       └─→ 不需要 → 继续
  │     └─→ 不是 → 继续
  │
  ├─→ 查看 wr context --limit=20
  │     ├─→ 发现 challenge_failure → 用 --js 或更新 cookie
  │     ├─→ 发现 auth_failure → wr cookie
  │     ├─→ 发现 fetch_failure(timeout) → 增加超时或减少任务
  │     └─→ 无异常 → 继续
  │
  └─→ 检查 completion
        ├─→ partial/incomplete → 根据 missing_outputs 修复
        └─→ complete 但内容不对 → 调整任务描述或工具选择
```

## 诊断命令速查

| 命令 | 用途 | 何时使用 |
|-----|------|---------|
| `wr doctor` | 环境检查 | 任务开始前/遇到异常后 |
| `wr auth-hint <url>` | 认证需求检测 | 访问平台详情页前 |
| `wr cookie <平台>` | 获取/更新 cookie | auth-hint 提示需要登录时 |
| `wr context --limit=N` | 查看执行痕迹 | 任务失败/异常后 |
| `wr skills --resolve` | 任务理解检查 | 不确定如何处理任务时 |
| `wr challenge-profiles` | 查看反爬支持 | 遇到 403/challenge 时 |
| `wr pressure` | 查看系统压力 | 任务频繁失败时 |
| `wr telemetry` | 综合状态检查 | 整体健康状况检查 |

## 修复命令速查

| 症状 | 修复命令 |
|-----|---------|
| 需要登录 | `wr cookie <平台>` |
| JS 动态内容 | `wr html <url> --js` |
| 超时 | `wr do "<任务>" --command-timeout-sec=180` |
| 结果不够 | `wr web "<query>" --crawl-pages=5` |
| 长任务 | `wr do-submit "<任务>"` |
| 环境损坏 | `wr doctor` + 按提示修复 |

## 预防性检查清单

任务执行前，确保已检查:

- [ ] `wr doctor` 全部通过
- [ ] 如果是平台任务，`wr auth-hint` 不提示需要登录
- [ ] 任务描述清晰（包含平台、数量、输出要求）
- [ ] 选择了合适的工具（不是滥用 `wr do`）
- [ ] 复杂任务已分阶段（resolve → plan → dry-run → execute）
- [ ] 知道失败后要执行哪些诊断命令
"""


def _content_for_kind(kind: str, repo_root: Path) -> str:
    skill_md = _skill_markdown(repo_root)
    if kind == "skill_md":
        return skill_md
    if kind == "cursor_rule":
        return _cursor_rule(skill_md)
    if kind == "agents_md":
        return _agents_md(skill_md)
    raise ValueError(f"unsupported content kind: {kind}")


def builtin_targets(repo_root: Optional[Path] = None, include_home: bool = True) -> List[InstallTarget]:
    root = (repo_root or _project_root()).resolve()
    home = Path.home()
    targets: List[InstallTarget] = [
        InstallTarget("web-rooter", root / ".web-rooter" / "ai-skills" / "web-rooter" / "SKILL.md", "skill_md"),
        InstallTarget("claude", root / ".claude" / "skills" / "web-rooter" / "SKILL.md", "skill_md"),
        InstallTarget("codex", root / "AGENTS.md", "agents_md"),
        InstallTarget("codex", root / ".agents" / "skills" / "web-rooter" / "SKILL.md", "skill_md"),
        InstallTarget("cursor", root / ".cursor" / "rules" / "web-rooter-cli.mdc", "cursor_rule"),
        InstallTarget("opencode", root / ".opencode" / "AGENTS.md", "agents_md"),
        InstallTarget("openclaw", root / ".openclaw" / "AGENTS.md", "agents_md"),
    ]
    if include_home:
        targets.extend(
            [
                InstallTarget("claude", home / ".claude" / "skills" / "web-rooter" / "SKILL.md", "skill_md", origin="home"),
                InstallTarget("codex", home / ".codex" / "AGENTS.md", "agents_md", origin="home"),
                InstallTarget("codex", home / ".agents" / "skills" / "web-rooter" / "SKILL.md", "skill_md", origin="home"),
                InstallTarget("cursor", home / ".cursor" / "rules" / "web-rooter-cli.mdc", "cursor_rule", origin="home"),
                InstallTarget("opencode", home / ".opencode" / "AGENTS.md", "agents_md", origin="home"),
                InstallTarget("openclaw", home / ".openclaw" / "AGENTS.md", "agents_md", origin="home"),
            ]
        )
    return targets


_SUPPORTED_CUSTOM_TOOLS = {
    "generic": "skill_md",
    "claude": "skill_md",
    "cursor": "cursor_rule",
    "codex": "agents_md",
    "agents": "agents_md",
    "opencode": "agents_md",
    "openclaw": "agents_md",
}


def _resolve_custom_target_path(base_path: Path, tool: str) -> tuple[Path, str]:
    normalized_tool = str(tool or "generic").strip().lower() or "generic"
    content_kind = _SUPPORTED_CUSTOM_TOOLS.get(normalized_tool, "skill_md")
    if base_path.suffix.lower() in {".md", ".mdc"}:
        return base_path, content_kind
    if normalized_tool == "cursor":
        return base_path / "web-rooter-cli.mdc", content_kind
    if normalized_tool in {"codex", "agents", "opencode", "openclaw"}:
        return base_path / "AGENTS.md", content_kind
    return base_path / "web-rooter" / "SKILL.md", content_kind


def custom_targets(repo_root: Optional[Path] = None) -> List[InstallTarget]:
    config = _load_config(repo_root)
    targets: List[InstallTarget] = []
    for item in config.get("custom_targets", []):
        if not isinstance(item, dict):
            continue
        raw_path = str(item.get("path") or "").strip()
        if not raw_path:
            continue
        tool = str(item.get("tool") or "generic").strip().lower() or "generic"
        target_path = Path(raw_path).expanduser()
        content_kind = str(item.get("content_kind") or "").strip()
        if not content_kind or target_path.suffix.lower() not in {".md", ".mdc"}:
            target_path, resolved_kind = _resolve_custom_target_path(target_path, tool)
            if not content_kind:
                content_kind = resolved_kind
        targets.append(InstallTarget(tool=tool, path=target_path, content_kind=content_kind or "skill_md", origin="custom"))
    return targets


def _troubleshooting_targets(repo_root: Optional[Path] = None, include_home: bool = True) -> List[InstallTarget]:
    """生成 TROUBLESHOOTING.md 的注入目标"""
    root = (repo_root or _project_root()).resolve()
    home = Path.home()
    targets: List[InstallTarget] = [
        # 与 SKILL.md 同目录的 TROUBLESHOOTING.md
        InstallTarget("web-rooter", root / ".web-rooter" / "ai-skills" / "web-rooter" / "TROUBLESHOOTING.md", "troubleshooting_md"),
        InstallTarget("claude", root / ".claude" / "skills" / "web-rooter" / "TROUBLESHOOTING.md", "troubleshooting_md"),
        InstallTarget("codex", root / ".agents" / "skills" / "web-rooter" / "TROUBLESHOOTING.md", "troubleshooting_md"),
    ]
    if include_home:
        targets.extend([
            InstallTarget("claude", home / ".claude" / "skills" / "web-rooter" / "TROUBLESHOOTING.md", "troubleshooting_md", origin="home"),
            InstallTarget("codex", home / ".agents" / "skills" / "web-rooter" / "TROUBLESHOOTING.md", "troubleshooting_md", origin="home"),
        ])
    return targets


def install_skills(repo_root: Optional[Path] = None, include_home: bool = True) -> Dict[str, Any]:
    root = (repo_root or _project_root()).resolve()
    records: List[Dict[str, Any]] = []
    
    # 生成主要内容
    all_targets = builtin_targets(root, include_home=include_home) + custom_targets(root)
    
    # 生成故障诊断文档目标
    all_targets.extend(_troubleshooting_targets(root, include_home=include_home))
    
    seen: set[tuple[str, str]] = set()
    for target in all_targets:
        key = (target.tool, str(target.path))
        if key in seen:
            continue
        seen.add(key)
        
        # 根据内容类型生成内容
        if target.content_kind == "troubleshooting_md":
            content = _troubleshooting_md()
        else:
            content = _content_for_kind(target.content_kind, root)
        
        status = _write_text(target.path, content)
        records.append(
            {
                "tool": target.tool,
                "path": str(target.path),
                "status": status,
                "content_kind": target.content_kind,
                "origin": target.origin,
            }
        )
    manifest = {
        "updated_at": _utc_now_iso(),
        "repo_root": str(root),
        "include_home": bool(include_home),
        "files": records,
    }
    manifest_path = _config_dir(root) / "manifest.json"
    _write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))
    return {"files": records, "manifest": str(manifest_path)}


def register_skills_dir(repo_root: Optional[Path], path: str, tool: str = "generic", write_now: bool = True) -> Dict[str, Any]:
    root = (repo_root or _project_root()).resolve()
    raw_base = Path(str(path)).expanduser()
    resolved_path, content_kind = _resolve_custom_target_path(raw_base, tool)

    config = _load_config(root)
    custom_targets = [item for item in config.get("custom_targets", []) if isinstance(item, dict)]
    record = {
        "tool": str(tool or "generic").strip().lower() or "generic",
        "path": str(raw_base),
        "content_kind": content_kind,
    }
    exists = any(
        str(item.get("tool") or "").strip().lower() == record["tool"]
        and str(item.get("path") or "").strip() == record["path"]
        for item in custom_targets
    )
    if not exists:
        custom_targets.append(record)
    config["custom_targets"] = custom_targets
    config_path = _save_config(config, root)

    write_status = "registered"
    final_target = InstallTarget(tool=record["tool"], path=resolved_path, content_kind=content_kind, origin="custom")
    if write_now:
        write_status = _write_text(final_target.path, _content_for_kind(final_target.content_kind, root))

    return {
        "success": True,
        "config_path": str(config_path),
        "registered": not exists,
        "tool": final_target.tool,
        "raw_path": str(raw_base),
        "target_path": str(final_target.path),
        "content_kind": final_target.content_kind,
        "write_status": write_status,
    }


def _detect_tool_installation_status(tool: str, repo_root: Path, include_home: bool = True) -> str:
    """检测 AI 工具的安装状态。
    
    返回: "installed" | "not_installed" | "unknown"
    """
    home = Path.home()
    
    # web-rooter: 项目自身的工具，总是视为已安装
    if tool == "web-rooter":
        return "installed"
    
    # claude: 检查 .claude 目录
    if tool == "claude":
        indicators = [repo_root / ".claude"]
        if include_home:
            indicators.append(home / ".claude")
        return "installed" if any(p.exists() for p in indicators) else "not_installed"
    
    # codex: 检查 AGENTS.md 或 .agents / .codex 目录
    if tool == "codex":
        indicators = [repo_root / "AGENTS.md", repo_root / ".agents"]
        if include_home:
            indicators.extend([home / ".codex", home / ".agents"])
        return "installed" if any(p.exists() for p in indicators) else "not_installed"
    
    # cursor: 检查 .cursor 目录
    if tool == "cursor":
        indicators = [repo_root / ".cursor"]
        if include_home:
            indicators.append(home / ".cursor")
        return "installed" if any(p.exists() for p in indicators) else "not_installed"
    
    # opencode: 检查 .opencode 目录
    if tool == "opencode":
        indicators = [repo_root / ".opencode"]
        if include_home:
            indicators.append(home / ".opencode")
        return "installed" if any(p.exists() for p in indicators) else "not_installed"
    
    # openclaw: 检查 .openclaw 目录
    if tool == "openclaw":
        indicators = [repo_root / ".openclaw"]
        if include_home:
            indicators.append(home / ".openclaw")
        return "installed" if any(p.exists() for p in indicators) else "not_installed"
    
    # 未知工具：默认视为已安装（让用户知道有这个工具）
    return "installed"


def doctor_skills(repo_root: Optional[Path] = None, include_home: bool = True) -> Dict[str, Any]:
    """检查 AI Skills 配置状态。
    
    按工具分组返回检查结果，每个工具显示一行：
    - 已安装且已配置: status="ok"
    - 已安装但未配置: status="missing" 
    - 未安装: status="not_installed"
    """
    root = (repo_root or _project_root()).resolve()
    
    # 收集所有目标
    all_targets = builtin_targets(root, include_home=include_home) + custom_targets(root)
    
    # 按工具分组统计
    tool_stats: Dict[str, Dict[str, Any]] = {}
    
    for target in all_targets:
        tool = target.tool
        if tool not in tool_stats:
            tool_stats[tool] = {
                "tool": tool,
                "targets": [],
                "any_exists": False,
                "any_marker_ok": False,
                "installed": False,  # 工具是否已安装
            }
        
        # 检查目标文件
        exists = target.path.exists()
        marker_ok = False
        if exists:
            try:
                content = target.path.read_text(encoding="utf-8", errors="ignore")
                marker_ok = SKILL_MARKER in content
            except Exception:
                marker_ok = False
        
        tool_stats[tool]["targets"].append({
            "path": str(target.path),
            "exists": exists,
            "marker_ok": marker_ok,
            "origin": target.origin,
        })
        
        if exists:
            tool_stats[tool]["any_exists"] = True
        if marker_ok:
            tool_stats[tool]["any_marker_ok"] = True
    
    # 检测每个工具的安装状态
    for tool in tool_stats:
        install_status = _detect_tool_installation_status(tool, root, include_home)
        tool_stats[tool]["installed"] = (install_status == "installed")
        tool_stats[tool]["install_status"] = install_status
    
    # 生成工具级别的检查结果（排除 web-rooter，因为不需要用户关心项目自身的配置）
    checks: List[Dict[str, Any]] = []
    for tool, stats in sorted(tool_stats.items()):
        # 跳过 web-rooter，只显示外部 AI 工具
        if tool == "web-rooter":
            continue
        installed = stats["installed"]
        has_valid_skill = stats["any_marker_ok"]
        
        if not installed:
            status = "not_installed"
        elif has_valid_skill:
            status = "ok"
        else:
            status = "missing"
        
        # 找到第一个有效的目标路径（用于显示）
        target_path = ""
        for t in stats["targets"]:
            if t["exists"] and t["marker_ok"]:
                target_path = t["path"]
                break
        if not target_path and stats["targets"]:
            target_path = stats["targets"][0]["path"]
        
        checks.append({
            "tool": tool,
            "status": status,  # ok | missing | not_installed
            "installed": installed,
            "has_valid_skill": has_valid_skill,
            "target_count": len(stats["targets"]),
            "path": target_path,
            "details": stats["targets"],
            "ok": status == "ok",
            "fix": (
                "run `wr skills-install` or `python scripts/setup_ai_skills.py`"
                if status == "missing"
                else ""
            ),
        })
    
    # 统计（排除 web-rooter）
    installed_tools = [c for c in checks if c["installed"]]
    ok_tools = [c for c in checks if c["status"] == "ok"]
    missing_tools = [c for c in checks if c["status"] == "missing"]
    not_installed_tools = [c for c in checks if c["status"] == "not_installed"]
    
    return {
        "success": True,
        "repo_root": str(root),
        "check_count": len(checks),
        "ok_count": len(ok_tools),
        "summary": {
            "total": len(checks),
            "ok": len(ok_tools),
            "missing": len(missing_tools),
            "not_installed": len(not_installed_tools),
            "installed_total": len(installed_tools),
            "installed_configured": len([c for c in installed_tools if c["status"] == "ok"]),
        },
        "checks": checks,
        "config_path": str(_config_path(root)),
    }

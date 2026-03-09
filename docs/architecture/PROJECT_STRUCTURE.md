# Project Structure (First Principles)

本文件定义仓库的“物理意义”边界，目标是保证开源维护时结构稳定、职责清晰。

## 1. 系统目标

输入：用户查询、URL、站点范围。  
输出：可追溯的搜索结果、抓取内容和提取信息。  
约束：优先稳定性、其次覆盖率，再考虑性能。

## 2. 分层模型

### Interface Layer

- `main.py`: CLI / MCP / HTTP server 启动分发
- `tools/`: MCP 工具协议适配
- `scripts/`: 跨平台安装/集成脚本（Windows + macOS/Linux）

### Orchestration Layer

- `agents/web_agent.py`: 任务编排（visit/search/research/crawl）

### Capability Layer (`core/`)

- `crawler.py`: HTTP 抓取、重试、缓存、连接池
- `browser.py`: Playwright 抓取与反检测
- `search/engine_base.py`: 配置驱动搜索流程
- `search/universal_parser.py`: 搜索结果解析与兜底提取
- `search/advanced.py`: 多引擎与深度搜索聚合
- `search/engine.py`, `search/graph.py`, `search/engine_config.py`: 搜索域内模型、图与配置
- 其它 `core/*`: 调度、会话、指标、存储等基础模块

兼容说明：

- `core/search_engine*.py`、`core/advanced_search.py`、`core/universal_parser.py` 等旧路径文件当前仅保留为 re-export 兼容层，避免破坏下游调用。
- 新增功能与维护应优先落在 `core/search/`。

### Configuration Layer

- `config.py`: 全局运行参数
- `core/engine-config/*.json`: 引擎配置

### Validation Layer

- `tests/`: 自动化校验
- `tests/manual/`: 手动回归脚本
- `main.py --doctor`: 运行时健康检查

### Reference Layer

- `temp/`: 外部项目快照（MindSearch / Scrapling / playwright-search-mcp / DocsGPT）
  - 仅做融合参考，不是运行时依赖

## 3. 目录契约

- 根目录只放入口、依赖、许可证和极少量顶层说明
- 有效文档统一放 `docs/`
- 历史文档统一放 `docs/archive/`
- 任何新功能都必须明确落在哪个层，不允许跨层直接耦合

## 4. 新增文件规则

- 运行时代码：`agents/` 或 `core/`
- 外部协议适配：`tools/`
- 用户文档：`docs/guide` 或 `docs/reference`
- 架构与设计：`docs/architecture`
- 临时分析、阶段报告：`docs/archive`（不进入当前文档主导航）

## 5. 开源维护建议

- 保持 README 只做入口，不堆积阶段性细节
- 每次发布只更新 `docs/` 下的当前文档，不回写 `archive/`
- 引擎行为变化时，同步更新 `core/engine-config` 与 `docs/reference`

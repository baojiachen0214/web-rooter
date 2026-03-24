# Micro Skills

细粒度 skills 用于给 AI 返回“当前这条命令最相关的小提示”，避免把不合适的工具匹配到不合适的任务。

推荐字段：
- `id`
- `title`
- `message`
- `commands`: 命令触发范围，如 `do` / `do-plan` / `quick`
- `keywords`: 任务文本关键词，命中后才触发
- `prefer_tools`
- `avoid_tools`
- `prefer_commands`
- `examples`
- `priority`

文件格式：`profiles/micro_skills/*.json`

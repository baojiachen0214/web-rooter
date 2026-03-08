# Web-Rooter 内存优化和缓存清理指南

**版本**: v2.1
**更新日期**: 2026-03-08

---

## 一、概述

Web-Rooter 提供了自动内存优化和缓存清理功能，确保：
- 搜索过程中产生的临时缓存及时清理
- 只保留最终结果
- 避免内存泄漏
- 提高长时间运行稳定性

---

## 二、缓存机制说明

### 2.1 缓存层级

Web-Rooter 使用两层缓存：

```
┌─────────────────────────────────────┐
│         内存缓存 (最快)              │
│  - 存储最近请求的 URL 响应             │
│  - TTL: 1 小时                       │
│  - 自动过期                          │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│       SQLite 持久化缓存 (较慢)        │
│  - 存储历史请求的 URL 响应             │
│  - TTL: 可配置                       │
│  - 跨会话保留                        │
└─────────────────────────────────────┘
```

### 2.2 缓存的优缺点

**优点**:
- 避免重复请求相同 URL
- 减少网络延迟
- 降低目标服务器压力

**缺点**:
- 占用内存
- 可能返回过期内容
- 需要清理机制

---

## 三、自动缓存清理

### 3.1 默认行为

从 v2.1 开始，Web-Rooter 默认启用自动缓存清理：

```python
# DeepSearchEngine 默认配置
deep_search = DeepSearchEngine(auto_cleanup=True)

# 搜索完成后自动清理中间缓存
result = await deep_search.deep_search(
    "查询关键词",
    crawl_top=5,
    auto_cleanup=True  # 默认清理
)
```

### 3.2 清理时机

缓存在以下时机被清理：

1. **搜索完成后** - `deep_search()` 返回后
2. **会话结束时** - `cleanup_search_session()` 调用后
3. **内存超限时** - 超过阈值自动触发

### 3.3 保留的内容

清理后保留的内容：
- ✅ 最终搜索结果（`result` 字典）
- ✅ 标记为"最终"的数据
- ✅ 用户明确保留的内容

清理后删除的内容：
- ❌ 搜索过程中的临时缓存
- ❌ 中间爬取结果（已整合到最终结果的除外）
- ❌ 过期的临时数据

---

## 四、手动控制缓存清理

### 4.1 禁用自动清理

如果需要保留缓存（例如多轮搜索相同 URL）：

```python
# 方法 1: 创建时禁用
deep_search = DeepSearchEngine(auto_cleanup=False)

# 方法 2: 调用时覆盖
result = await deep_search.deep_search(
    "查询",
    auto_cleanup=False  # 不清理
)
```

### 4.2 手动清理

```python
from core.memory_optimizer import cleanup_search_session

# 清理会话，保留最终结果
await cleanup_search_session(keep_final_results=True)

# 清理所有（包括最终结果）
await cleanup_search_session(keep_final_results=False)
```

### 4.3 标记最终结果

```python
from core.memory_optimizer import mark_result_as_final

# 标记某个结果为最终结果（不会被清理）
mark_result_as_final("result_key")
```

---

## 五、内存监控

### 5.1 查看内存使用

```python
from core.memory_optimizer import get_memory_optimizer

optimizer = get_memory_optimizer()
stats = optimizer.check_memory_usage()

print(f"当前内存：{stats['rss_mb']:.1f}MB")
print(f"内存使用率：{stats['percent']:.1f}%")
print(f"跟踪缓存数：{stats['tracked_caches']}")
print(f"临时结果数：{stats['temp_results']}")
```

### 5.2 内存阈值

默认内存阈值为 500MB，超过时自动触发清理：

```python
# 修改阈值
optimizer = MemoryOptimizer(memory_threshold_mb=1000)  # 1GB
```

### 5.3 统计信息

```python
stats = optimizer.get_stats()
print(stats)

# 输出示例:
# {
#     "cleanup_count": 5,
#     "last_cleanup": "2026-03-08T20:30:00",
#     "tracked_caches": 0,
#     "temp_results": 0,
#     "memory_usage": {...}
# }
```

---

## 六、最佳实践

### 6.1 推荐配置

**单次搜索任务**:
```python
deep_search = DeepSearchEngine(auto_cleanup=True)
result = await deep_search.deep_search("查询")
# 自动清理，只保留 result
```

**多轮迭代搜索**:
```python
deep_search = DeepSearchEngine(auto_cleanup=False)

# 第一轮
result1 = await deep_search.deep_search("查询 1")

# 第二轮
result2 = await deep_search.deep_search("查询 2")

# 完成后清理
await cleanup_search_session()
```

**批量搜索**:
```python
deep_search = DeepSearchEngine(auto_cleanup=False)

queries = ["查询 1", "查询 2", "查询 3"]
results = []

for query in queries:
    result = await deep_search.deep_search(query)
    results.append(result)

# 全部完成后清理
await cleanup_search_session()
```

### 6.2 避免内存泄漏

```python
# ✅ 推荐：使用上下文管理器
async with Crawler() as crawler:
    result = await crawler.fetch(url)
# 自动关闭和清理

# ❌ 避免：不关闭 crawler
crawler = Crawler()
result = await crawler.fetch(url)
# 忘记关闭
```

### 6.3 大文件处理

如果爬取大量页面：

```python
# 分批次处理
batch_size = 10
for i in range(0, len(urls), batch_size):
    batch = urls[i:i+batch_size]

    # 处理批次
    tasks = [crawler.fetch(url) for url in batch]
    results = await asyncio.gather(*tasks)

    # 每批后清理
    await cleanup_search_session()
```

---

## 七、API 参考

### 7.1 MemoryOptimizer

```python
class MemoryOptimizer:
    def __init__(self, auto_cleanup: bool = True, memory_threshold_mb: int = 500)

    def check_memory_usage() -> Dict[str, Any]
    async def cleanup(force: bool = False)
    def get_stats() -> Dict[str, Any]
```

### 7.2 SearchSessionCleaner

```python
class SearchSessionCleaner:
    def mark_as_final(cache_key: str)
    async def cleanup_session(keep_final: bool = True)
    def get_session_stats() -> Dict[str, Any]
```

### 7.3 便捷函数

```python
# 获取全局优化器
get_memory_optimizer() -> MemoryOptimizer

# 获取会话清理器
get_session_cleaner() -> SearchSessionCleaner

# 清理会话
cleanup_search_session(keep_final_results: bool = True)

# 标记最终结果
mark_result_as_final(cache_key: str)

# 检查并清理
check_and_cleanup_memory()
```

---

## 八、常见问题

### Q1: 缓存清理会影响性能吗？

**A**: 清理本身很快（<100ms），但清理后再次请求相同 URL 会重新获取。建议：
- 单次任务：启用自动清理
- 多轮相同 URL 搜索：禁用自动清理

### Q2: 如何确认缓存已被清理？

**A**: 使用内存监控：
```python
stats = get_memory_optimizer().get_stats()
print(f"tracked_caches: {stats['tracked_caches']}")
print(f"temp_results: {stats['temp_results']}")
# 清理后应该接近 0
```

### Q3: 清理后还能访问之前的结果吗？

**A**: 可以。清理只删除内部缓存，不影响返回的 `result` 字典：
```python
result = await deep_search.deep_search("查询")
# 清理后 result 仍然可用
await cleanup_search_session()
print(result['total_results'])  # 正常访问
```

### Q4: 内存阈值设置多少合适？

**A**:
- 一般使用：500MB（默认）
- 大量并发：1000-2000MB
- 资源受限：200-300MB

---

## 九、性能调优

### 9.1 禁用缓存（极端情况）

如果不需要缓存（例如每次都是不同 URL）：

```python
crawler = Crawler(use_cache=False)
```

### 9.2 调整缓存 TTL

```python
crawler = Crawler(cache_ttl=300)  # 5 分钟
```

### 9.3 使用纯内存缓存

```python
# 不使用 SQLite 持久化
crawler = Crawler(use_cache=True, cache_db_path=None)
```

---

## 十、总结

**默认配置即可满足大部分场景**:
```python
deep_search = DeepSearchEngine(auto_cleanup=True)
result = await deep_search.deep_search("查询")
```

**特殊需求时手动控制**:
- 多轮搜索：禁用自动清理
- 内存受限：降低阈值
- 长时间运行：定期手动清理

**核心原则**:
1. 第一手资料优先
2. 只保留最终结果
3. 及时清理中间缓存
4. 避免内存泄漏

"""
搜索图结构 - 支持多子问题并行搜索

灵感来自 MindSearch 的 WebSearchGraph

功能:
- 图结构管理搜索节点
- 并行执行多个搜索任务
- 支持节点依赖关系
- 流式结果输出
"""
import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, AsyncGenerator
import logging
import json

logger = logging.getLogger(__name__)


@dataclass
class SearchNode:
    """搜索节点"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    query: str = ""
    parent_id: Optional[str] = None
    status: str = "pending"  # pending, executing, completed, failed
    results: List[Any] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "query": self.query,
            "parent_id": self.parent_id,
            "status": self.status,
            "results": self.results,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "metadata": self.metadata,
        }


class SearchGraph:
    """
    搜索图 - 管理多子问题并行搜索

    用法:
        graph = SearchGraph()
        root_id = graph.add_query("AI 发展历史", is_root=True)
        graph.add_query("AI 技术演进", parent_id=root_id)
        graph.add_query("AI 未来趋势", parent_id=root_id)
        results = await graph.execute_all()
    """

    def __init__(
        self,
        max_workers: int = 8,
        search_engine: Optional[Any] = None,
    ):
        """
        初始化搜索图

        Args:
            max_workers: 最大并发工作线程数
            search_engine: 搜索引擎实例
        """
        self.nodes: Dict[str, SearchNode] = {}
        self.edges: Dict[str, List[str]] = defaultdict(list)
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._search_engine = search_engine
        self.root_id: Optional[str] = None
        self._result_queue = asyncio.Queue()

    def add_query(
        self,
        query: str,
        parent_id: Optional[str] = None,
        is_root: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        添加查询节点

        Args:
            query: 搜索查询
            parent_id: 父节点 ID
            is_root: 是否为根节点
            metadata: 额外元数据

        Returns:
            节点 ID
        """
        node_id = str(uuid.uuid4())
        self.nodes[node_id] = SearchNode(
            id=node_id,
            query=query,
            parent_id=parent_id,
            metadata=metadata or {},
        )

        if is_root:
            self.root_id = node_id
        elif parent_id:
            self.edges[parent_id].append(node_id)

        logger.debug(f"Added query node: {node_id} - {query[:50]}...")
        return node_id

    async def _execute_node(self, node_id: str) -> SearchNode:
        """
        执行单个节点搜索

        Args:
            node_id: 节点 ID

        Returns:
            更新后的节点
        """
        node = self.nodes[node_id]
        node.status = "executing"

        # 通知节点开始执行
        await self._result_queue.put(("node_start", node.to_dict()))

        try:
            # 确保搜索引擎初始化
            if self._search_engine is None:
                from core.search.engine import MultiSearchEngine
                self._search_engine = MultiSearchEngine()

            # 执行搜索
            results = await self._search_engine.search(
                node.query,
                deduplicate=True,
                parallel=True,
            )
            node.results = [r.to_dict() if hasattr(r, 'to_dict') else r for r in results]
            node.status = "completed"
            logger.info(f"Node {node_id} completed with {len(node.results)} results")

        except Exception as e:
            logger.error(f"Node {node_id} failed: {e}")
            node.status = "failed"
            node.error = str(e)

        finally:
            node.completed_at = datetime.now()

        # 通知节点完成
        await self._result_queue.put(("node_complete", node.to_dict()))

        return node

    async def execute_all(self) -> Dict[str, SearchNode]:
        """
        执行所有节点

        Returns:
            所有节点的结果
        """
        if not self.nodes:
            logger.warning("No nodes to execute")
            return {}

        logger.info(f"Executing {len(self.nodes)} search nodes...")

        # 创建所有节点的任务
        tasks = [self._execute_node(node_id) for node_id in self.nodes]

        # 等待所有任务完成
        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info(f"All nodes completed. Results: {self.get_stats()}")

        return self.nodes

    async def execute_stream(self) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式执行所有节点

        Yields:
            节点状态更新
        """
        if not self.nodes:
            return

        # 创建任务
        async def run_node(node_id: str):
            try:
                await self._execute_node(node_id)
            except Exception as e:
                logger.error(f"Node {node_id} error: {e}")

        tasks = [asyncio.create_task(run_node(nid)) for nid in self.nodes]

        # 从队列中获取更新
        pending_tasks = len(tasks)
        while pending_tasks > 0:
            try:
                event_type, data = await asyncio.wait_for(
                    self._result_queue.get(),
                    timeout=1.0,
                )
                yield {
                    "event": event_type,
                    "data": data,
                }
            except asyncio.TimeoutError:
                # 检查任务是否完成
                done = sum(1 for t in tasks if t.done())
                if done == len(tasks):
                    break

        yield {
            "event": "complete",
            "data": self.get_results(),
        }

    def get_results(self) -> Dict[str, Any]:
        """获取结果"""
        return {
            "nodes": {
                node_id: node.to_dict()
                for node_id, node in self.nodes.items()
            },
            "edges": dict(self.edges),
            "stats": self.get_stats(),
        }

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        status_counts = defaultdict(int)
        for node in self.nodes.values():
            status_counts[node.status] += 1

        total_results = sum(len(node.results) for node in self.nodes.values())

        return {
            "total_nodes": len(self.nodes),
            "completed": status_counts.get("completed", 0),
            "failed": status_counts.get("failed", 0),
            "pending": status_counts.get("pending", 0),
            "total_results": total_results,
        }

    def reset(self):
        """重置图"""
        self.nodes.clear()
        self.edges.clear()
        self.root_id = None


class MindSearchStyleAgent:
    """
    类似 MindSearch 的搜索代理

    使用 SearchGraph 进行多轮搜索
    """

    def __init__(
        self,
        search_engine: Optional[Any] = None,
        max_workers: int = 8,
        max_turns: int = 5,
    ):
        self.search_engine = search_engine
        self.max_workers = max_workers
        self.max_turns = max_turns
        self._search_history = []

    def decompose_query(self, query: str) -> List[str]:
        """
        将复杂查询分解为多个子问题

        实际应用中可以使用 LLM 来分解
        这里使用简单的规则作为示例
        """
        # 示例：分解为几个方面
        sub_queries = []

        # 基础查询
        sub_queries.append(query)

        # 添加一些相关的子问题
        query_keywords = query.split()
        if len(query_keywords) > 1:
            for keyword in query_keywords[:3]:
                if len(keyword) > 2:
                    sub_queries.append(f"{keyword} {query}")

        return sub_queries[:self.max_turns]

    async def research(self, query: str) -> Dict[str, Any]:
        """
        研究一个主题

        Args:
            query: 研究主题

        Returns:
            研究结果
        """
        logger.info(f"Starting research on: {query}")

        # 分解查询
        sub_queries = self.decompose_query(query)
        logger.info(f"Decomposed into {len(sub_queries)} sub-queries: {sub_queries}")

        # 创建搜索图
        graph = SearchGraph(
            max_workers=self.max_workers,
            search_engine=self.search_engine,
        )

        # 添加根节点
        root_id = graph.add_query(sub_queries[0], is_root=True)

        # 添加子问题节点
        for sub_query in sub_queries[1:]:
            graph.add_query(sub_query, parent_id=root_id)

        # 执行搜索
        await graph.execute_all()

        # 获取结果
        results = graph.get_results()
        self._search_history.append({
            "query": query,
            "timestamp": datetime.now().isoformat(),
            "results": results,
        })

        return results

    async def research_stream(self, query: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式研究一个主题

        Args:
            query: 研究主题

        Yields:
            研究结果更新
        """
        logger.info(f"Starting streaming research on: {query}")

        # 分解查询
        sub_queries = self.decompose_query(query)

        # 创建搜索图
        graph = SearchGraph(
            max_workers=self.max_workers,
            search_engine=self.search_engine,
        )

        # 添加根节点
        root_id = graph.add_query(sub_queries[0], is_root=True)
        yield {
            "event": "query_decomposed",
            "data": {"root_query": sub_queries[0]},
        }

        # 添加子问题节点
        for i, sub_query in enumerate(sub_queries[1:], 1):
            node_id = graph.add_query(sub_query, parent_id=root_id)
            yield {
                "event": "sub_query_added",
                "data": {
                    "id": node_id,
                    "query": sub_query,
                    "index": i,
                },
            }

        # 流式执行搜索
        async for update in graph.execute_stream():
            yield update

        self._search_history.append({
            "query": query,
            "timestamp": datetime.now().isoformat(),
        })


async def main():
    """示例用法"""
    # 创建代理
    agent = MindSearchStyleAgent(max_workers=4, max_turns=3)

    # 研究主题
    query = "人工智能发展历史"
    print(f"研究主题：{query}\n")

    # 流式研究
    async for update in agent.research_stream(query):
        event_type = update.get("event", "unknown")
        if event_type == "query_decomposed":
            print(f"根查询：{update['data']['root_query']}")
        elif event_type == "sub_query_added":
            data = update['data']
            print(f"添加子查询 {data['index']}: {data['query']}")
        elif event_type == "node_start":
            print(f"开始执行节点：{update['data']['query'][:30]}...")
        elif event_type == "node_complete":
            data = update['data']
            print(f"完成节点：{data['query'][:30]}... - {data['status']} ({len(data['results'])} 结果)")
        elif event_type == "complete":
            print(f"\n研究完成!")
            print(f"总节点数：{update['data']['stats']['total_nodes']}")
            print(f"完成：{update['data']['stats']['completed']}")
            print(f"总结果数：{update['data']['stats']['total_results']}")


if __name__ == "__main__":
    asyncio.run(main())

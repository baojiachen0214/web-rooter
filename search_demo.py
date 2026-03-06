"""
搜索功能演示脚本
"""
import asyncio
from core.search_engine import (
    SearchEngine,
    web_search,
    web_search_multi,
    web_search_smart,
    MultiSearchEngine,
)
from agents.web_agent import WebAgent


async def demo_single_search():
    """单引擎搜索演示"""
    print("=" * 50)
    print("【演示 1】单引擎搜索：Python 最新特性")
    print("=" * 50)

    result = await web_search("Python 2025 新特性", SearchEngine.BING, num_results=5)

    if result.error:
        print(f"搜索失败：{result.error}")
    else:
        print(f"引擎：{result.engine}")
        print(f"搜索耗时：{result.search_time:.2f}秒")
        print(f"结果数量：{result.total_results}")
        print()
        for r in result.results:
            print(f"[{r.rank}] {r.title}")
            print(f"    URL: {r.url}")
            print(f"    {r.snippet[:100]}...")
            print()


async def demo_multi_search():
    """多引擎并行搜索演示"""
    print("=" * 50)
    print("【演示 2】多引擎并行搜索：AI 大模型")
    print("=" * 50)

    multi = MultiSearchEngine()
    responses = await multi.search(
        "AI 大模型 2025 最新进展",
        engines=[SearchEngine.BING, SearchEngine.BAIDU],
        num_results=5,
    )
    await multi.close()

    for response in responses:
        if response.error:
            print(f"[{response.engine}] 失败：{response.error}")
        else:
            print(f"[{response.engine}] 找到 {response.total_results} 个结果")
            for r in response.results[:3]:
                print(f"  - {r.title}")
        print()


async def demo_combined_search():
    """组合搜索演示"""
    print("=" * 50)
    print("【演示 3】组合搜索：机器学习入门")
    print("=" * 50)

    multi = MultiSearchEngine()
    response = await multi.search_combined(
        "机器学习入门教程",
        total_results=10,
    )
    await multi.close()

    print(f"合并结果：{response.total_results} 个唯一结果")
    print()
    for i, r in enumerate(response.results[:5], 1):
        print(f"[{i}] {r.title} ({r.engine})")
        print(f"    {r.url}")
        print()


async def demo_smart_search():
    """智能深度搜索演示"""
    print("=" * 50)
    print("【演示 4】智能深度搜索：什么是量子计算")
    print("=" * 50)

    result = await web_search_smart("什么是量子计算", max_depth=2)

    if result.get("success"):
        print(f"搜索完成")
        print(f"搜索结果：{len(result['search_results']['results'])} 个")
        print(f"已爬取页面：{len(result['crawled_pages'])} 个")
        print()
        for page in result['crawled_pages'][:2]:
            print(f"[{page['title']}]")
            print(f"{page['content'][:300]}...")
            print()
    else:
        print(f"搜索失败：{result.get('error')}")


async def demo_agent_search():
    """Agent 互联网搜索演示"""
    print("=" * 50)
    print("【演示 5】Web Agent 互联网搜索：深度学习框架对比")
    print("=" * 50)

    async with WebAgent() as agent:
        result = await agent.search_internet(
            "深度学习框架 PyTorch TensorFlow 对比",
            num_results=5,
            auto_crawl=True,
        )

        print(result.content[:2000])


async def demo_research():
    """深度研究演示"""
    print("=" * 50)
    print("【演示 6】深度研究：Transformer 架构")
    print("=" * 50)

    async with WebAgent() as agent:
        result = await agent.research_topic(
            "Transformer 架构原理",
            max_searches=2,
            max_pages=5,
        )

        print(result.content[:2000])


async def main():
    """主函数"""
    print("Web-Rooter 搜索功能演示\n")

    # 选择要运行的演示
    demos = {
        "1": demo_single_search,
        "2": demo_multi_search,
        "3": demo_combined_search,
        "4": demo_smart_search,
        "5": demo_agent_search,
        "6": demo_research,
    }

    print("选择演示:")
    print("1. 单引擎搜索")
    print("2. 多引擎并行搜索")
    print("3. 组合搜索（去重合并）")
    print("4. 智能深度搜索（搜索 + 爬取）")
    print("5. Web Agent 搜索")
    print("6. 深度研究")
    print("a. 运行所有演示")
    print()

    choice = input("请输入选项 (1-6 或 a): ").strip()

    if choice == "a":
        for demo_func in demos.values():
            try:
                await demo_func()
            except Exception as e:
                print(f"演示出错：{e}")
    elif choice in demos:
        await demos[choice]()
    else:
        print("无效选项")


if __name__ == "__main__":
    asyncio.run(main())

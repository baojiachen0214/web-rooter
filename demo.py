"""
快速启动脚本 - 不依赖浏览器
"""
import asyncio
import sys
import os

# 设置 UTF-8 编码
os.environ['PYTHONIOENCODING'] = 'utf-8'

from core.crawler import Crawler
from core.parser import Parser
from agents.web_agent import WebAgent


async def demo():
    """演示基本功能"""
    print("=" * 50)
    print("Web-Rooter 演示")
    print("=" * 50)

    # 不使用浏览器的简单 Agent
    agent = WebAgent()
    await agent._init()

    try:
        # 访问网页
        print("\n访问 https://example.com ...")
        result = await agent.visit("https://example.com", use_browser=False)

        if result.success:
            print(f"标题：{result.data.get('title', 'N/A')}")
            print(f"\n内容预览:")
            print(result.content[:500])

            # 搜索
            print("\n" + "=" * 50)
            print("搜索 'Example' ...")
            search = await agent.search("Example")
            print(search.content)
        else:
            print(f"失败：{result.error}")
    finally:
        await agent.close()

    print("\n" + "=" * 50)
    print("演示完成!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(demo())

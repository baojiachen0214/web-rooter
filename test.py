"""
测试脚本
"""
import asyncio
import sys
import os

# 设置 UTF-8 编码
os.environ['PYTHONIOENCODING'] = 'utf-8'

from agents.web_agent import WebAgent
from core.crawler import Crawler
from core.parser import Parser
from core.browser import BrowserManager


async def test_crawler():
    """测试爬虫"""
    print("=" * 50)
    print("测试爬虫")
    print("=" * 50)

    async with Crawler() as crawler:
        result = await crawler.fetch("https://example.com")
        print(f"URL: {result.url}")
        print(f"Status: {result.status_code}")
        print(f"Response Time: {result.response_time:.2f}s")
        print(f"Content Length: {len(result.html)}")
        print(f"Success: {result.success}")
        if result.html:
            print(f"First 200 chars: {result.html[:200]}...")


async def test_parser():
    """测试解析器"""
    print("\n" + "=" * 50)
    print("测试解析器")
    print("=" * 50)

    html = """
    <html>
        <head>
            <title>测试页面</title>
            <meta name="description" content="这是一个测试页面">
        </head>
        <body>
            <h1>欢迎来到测试页面</h1>
            <p>这是第一段内容。</p>
            <p>这是第二段内容。</p>
            <a href="/link1">链接 1</a>
            <a href="/link2">链接 2</a>
            <img src="/image.jpg" alt="测试图片">
        </body>
    </html>
    """

    parser = Parser().parse(html, "https://example.com")
    extracted = parser.extract()

    print(f"Title: {extracted.title}")
    print(f"Text: {extracted.text[:100]}...")
    print(f"Links: {len(extracted.links)}")
    print(f"Images: {len(extracted.images)}")
    print(f"Metadata: {extracted.metadata}")


async def test_agent():
    """测试 Agent"""
    print("\n" + "=" * 50)
    print("测试 Web Agent")
    print("=" * 50)

    async with WebAgent() as agent:
        # 测试访问
        print("\n访问 example.com...")
        result = await agent.visit("https://example.com")
        print(f"Success: {result.success}")
        print(f"Title: {result.data.get('title') if result.data else 'N/A'}")

        # 测试搜索
        print("\n搜索 'example'...")
        search_result = await agent.search("example")
        print(f"Found: {search_result.success}")

        # 获取知识库
        print("\n知识库:")
        kb = agent.get_knowledge_base()
        for item in kb:
            print(f"  - {item['title']}")


async def test_browser():
    """测试浏览器"""
    print("\n" + "=" * 50)
    print("测试 Browser (需要安装 playwright)")
    print("=" * 50)

    try:
        async with BrowserManager() as browser:
            result = await browser.fetch("https://example.com")
            print(f"Title: {result.title}")
            print(f"HTML Length: {len(result.html)}")
            print(f"Error: {result.error}")
    except Exception as e:
        print(f"Browser 测试跳过：{e}")
        print("提示：运行 'playwright install chromium' 安装浏览器")


async def main():
    """运行所有测试"""
    print("[Web-Rooter] 测试套件\n")

    try:
        await test_crawler()
    except Exception as e:
        print(f"Crawler 测试失败：{e}")

    try:
        await test_parser()
    except Exception as e:
        print(f"Parser 测试失败：{e}")

    try:
        await test_agent()
    except Exception as e:
        print(f"Agent 测试失败：{e}")

    try:
        await test_browser()
    except Exception as e:
        print(f"Browser 测试跳过：{e}")

    print("\n" + "=" * 50)
    print("测试完成!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())

"""
Web-Rooter - AI Web Crawling Agent
主入口文件
"""
import asyncio
import argparse
import json
import sys
from typing import Optional
import logging

from agents.web_agent import WebAgent
from tools.mcp_tools import WebTools, run_mcp_server
from config import crawler_config, browser_config
from core.academic_search import AcademicSource

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class WebRooterCLI:
    """命令行界面"""

    def __init__(self):
        self.agent: Optional[WebAgent] = None
        self.tools: Optional[WebTools] = None

    async def start(self):
        """启动"""
        self.agent = WebAgent()
        await self.agent._init()
        self.tools = WebTools()
        await self.tools.initialize()
        print("[Web]  Web-Rooter 已启动")
        print("输入 'help' 查看可用命令")
        print()

    async def stop(self):
        """停止"""
        if self.agent:
            await self.agent.close()
        if self.tools:
            await self.tools.close()
        print("Bye 再见!")

    async def run_command(self, command: str, args: list[str]) -> bool:
        """运行命令"""
        if command == "visit" and args:
            url = args[0]
            use_browser = "--js" in args
            result = await self.agent.visit(url, use_browser=use_browser)
            self._print_result(result)

        elif command == "search" and args:
            query = args[0]
            url = args[1] if len(args) > 1 else None
            result = await self.agent.search(query, url)
            self._print_result(result)

        elif command == "extract" and len(args) >= 2:
            url = args[0]
            target = " ".join(args[1:])
            result = await self.agent.extract(url, target)
            self._print_result(result)

        elif command == "crawl" and args:
            url = args[0]
            max_pages = 10
            max_depth = 3
            for i, arg in enumerate(args[1:], 1):
                if arg.isdigit():
                    if i == 1:
                        max_pages = int(arg)
                    elif i == 2:
                        max_depth = int(arg)
            result = await self.agent.crawl(url, max_pages, max_depth)
            self._print_result(result)

        elif command == "links" and args:
            url = args[0]
            internal_only = "--internal" not in args
            result = await self.tools.get_links(url, internal_only=internal_only)
            self._print_result(result)

        elif command == "kb" or command == "knowledge":
            result = await self.tools.get_knowledge_base()
            self._print_result(result)

        elif command == "fetch" and args:
            url = args[0]
            result = await self.tools.fetch(url)
            self._print_result(result)

        elif command == "web" and args:
            # 互联网搜索命令
            query = " ".join(args)
            result = await self.agent.search_internet(query, auto_crawl=True)
            self._print_result(result)

        elif command == "research" and args:
            # 深度研究主题
            topic = " ".join(args)
            result = await self.agent.research_topic(topic)
            self._print_result(result)

        elif command == "academic" and args:
            # 学术模式搜索
            query = " ".join(args)
            result = await self.agent.search_academic(query, include_code=True)
            self._print_result(result)

        elif command == "site" and len(args) >= 2:
            # 站内搜索
            url = args[0]
            query = " ".join(args[1:])
            result = await self.agent.search_with_form(url, query)
            self._print_result(result)

        elif command == "help":
            self._print_help()

        elif command == "quit" or command == "exit":
            return False

        else:
            print(f"Error: 未知命令：{command}")
            print("输入 'help' 查看可用命令")

        return True

    def _print_result(self, result):
        """打印结果"""
        if hasattr(result, "to_dict"):
            result = result.to_dict()

        if isinstance(result, dict):
            print(json.dumps(result, ensure_ascii=False, indent=2)[:5000])
        else:
            print(result)

    def _print_help(self):
        """打印帮助"""
        help_text = """
Guide 可用命令:

  visit <url> [--js]     - 访问网页 (--js 使用浏览器)
  search <query> [url]   - 在已访问页面中搜索
  extract <url> <target> - 提取特定信息
  crawl <url> [pages] [depth] - 爬取网站
  links <url> [--all]    - 获取链接
  kb / knowledge         - 查看知识库
  fetch <url>            - 获取页面

互联网搜索命令:
  web <query>            - 互联网搜索（多引擎）
  web <query> --no-crawl - 仅搜索不爬取
  research <topic>       - 深度研究主题

学术模式命令:
  academic <query>       - 学术搜索（论文/代码项目）
  academic <query> --papers-only - 仅搜索论文

站内搜索命令:
  site <url> <query>     - 在网站内搜索

示例:
  visit https://example.com
  visit https://example.com --js
  search Python 新闻
  extract https://news.com 最新的头条新闻
  crawl https://example.com 5 2
  links https://example.com --all
  web AI 大模型 2025 最新进展
  research 机器学习入门
  academic Transformer 架构
  site https://github.com AI framework
"""
        print(help_text)


async def interactive_mode():
    """交互模式"""
    cli = WebRooterCLI()
    await cli.start()

    try:
        while True:
            try:
                user_input = input("> web-rooter> ").strip()
            except EOFError:
                break

            if not user_input:
                continue

            parts = user_input.split()
            command = parts[0]
            args = parts[1:]

            should_continue = await cli.run_command(command, args)
            if not should_continue:
                break

    finally:
        await cli.stop()


async def command_mode(command: str, args: list[str]):
    """命令行模式"""
    cli = WebRooterCLI()
    await cli.start()

    try:
        await cli.run_command(command, args)
    finally:
        await cli.stop()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="[Web]  Web-Rooter - AI Web Crawling Agent"
    )

    parser.add_argument(
        "--mcp",
        action="store_true",
        help="运行 MCP 服务器"
    )

    parser.add_argument(
        "--server",
        action="store_true",
        help="运行 HTTP 服务器"
    )

    parser.add_argument(
        "command",
        nargs="?",
        help="要执行的命令"
    )

    parser.add_argument(
        "args",
        nargs="*",
        help="命令参数"
    )

    args = parser.parse_args()

    if args.mcp:
        print("[MCP] 启动 MCP 服务器...")
        asyncio.run(run_mcp_server())
    elif args.server:
        print("[API] 启动 HTTP 服务器...")
        from server import run_http_server
        asyncio.run(run_http_server())
    elif args.command:
        asyncio.run(command_mode(args.command, args.args))
    else:
        asyncio.run(interactive_mode())


if __name__ == "__main__":
    main()

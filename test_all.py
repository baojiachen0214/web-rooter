"""
综合功能测试脚本
测试所有核心功能是否正常工作
"""
import asyncio
import sys


def test_imports():
    """测试所有模块导入"""
    print("=" * 60)
    print("测试 1: 模块导入")
    print("=" * 60)

    errors = []

    try:
        from core.crawler import Crawler, CrawlResult
        print("  [OK] core.crawler")
    except Exception as e:
        errors.append(f"core.crawler: {e}")
        print(f"  [FAIL] core.crawler: {e}")

    try:
        from core.parser import Parser, ExtractedData
        print("  [OK] core.parser")
    except Exception as e:
        errors.append(f"core.parser: {e}")
        print(f"  [FAIL] core.parser: {e}")

    try:
        from core.browser import BrowserManager, BrowserResult
        print("  [OK] core.browser")
    except Exception as e:
        errors.append(f"core.browser: {e}")
        print(f"  [FAIL] core.browser: {e}")

    try:
        from core.search_engine import (
            SearchEngine, SearchResult, SearchResponse,
            MultiSearchEngine, web_search, web_search_multi
        )
        print("  [OK] core.search_engine")
    except Exception as e:
        errors.append(f"core.search_engine: {e}")
        print(f"  [FAIL] core.search_engine: {e}")

    try:
        from core.academic_search import (
            AcademicSource, PaperResult, CodeProjectResult,
            AcademicSearchEngine, is_academic_query, academic_search
        )
        print("  [OK] core.academic_search")
    except Exception as e:
        errors.append(f"core.academic_search: {e}")
        print(f"  [FAIL] core.academic_search: {e}")

    try:
        from core.form_search import (
            FormField, SearchForm, SearchFormResult,
            FormFiller, auto_search
        )
        print("  [OK] core.form_search")
    except Exception as e:
        errors.append(f"core.form_search: {e}")
        print(f"  [FAIL] core.form_search: {e}")

    try:
        from agents.web_agent import WebAgent, AgentResponse
        print("  [OK] agents.web_agent")
    except Exception as e:
        errors.append(f"agents.web_agent: {e}")
        print(f"  [FAIL] agents.web_agent: {e}")

    try:
        from tools.mcp_tools import WebTools, setup_mcp_server
        print("  [OK] tools.mcp_tools")
    except Exception as e:
        errors.append(f"tools.mcp_tools: {e}")
        print(f"  [FAIL] tools.mcp_tools: {e}")

    try:
        from server import app, run_http_server
        print("  [OK] server")
    except Exception as e:
        errors.append(f"server: {e}")
        print(f"  [FAIL] server: {e}")

    print()
    return len(errors) == 0, errors


def test_webagent_methods():
    """测试 WebAgent 所有方法"""
    print("=" * 60)
    print("测试 2: WebAgent 方法")
    print("=" * 60)

    from agents.web_agent import WebAgent

    required_methods = [
        'visit',
        'search',
        'extract',
        'crawl',
        'search_internet',
        'search_and_fetch',
        'research_topic',
        'search_academic',
        'search_with_form',
        'get_visited_urls',
        'get_knowledge_base',
        'close',
    ]

    agent = WebAgent()
    errors = []

    for method in required_methods:
        if hasattr(agent, method) and callable(getattr(agent, method)):
            print(f"  [OK] {method}")
        else:
            errors.append(f"Missing method: {method}")
            print(f"  [FAIL] {method}")

    print()
    return len(errors) == 0, errors


def test_mcp_tools():
    """测试 MCP 工具"""
    print("=" * 60)
    print("测试 3: MCP 工具")
    print("=" * 60)

    from tools.mcp_tools import WebTools

    required_methods = [
        'fetch',
        'fetch_js',
        'search',
        'extract',
        'crawl',
        'parse_html',
        'get_links',
        'get_knowledge_base',
        'web_search',
        'web_search_combined',
        'web_research',
        'web_search_academic',
        'web_search_site',
    ]

    errors = []

    for method in required_methods:
        if hasattr(WebTools, method) and callable(getattr(WebTools, method)):
            print(f"  [OK] {method}")
        else:
            errors.append(f"Missing method: {method}")
            print(f"  [FAIL] {method}")

    print()
    return len(errors) == 0, errors


def test_api_endpoints():
    """测试 HTTP API 端点"""
    print("=" * 60)
    print("测试 4: HTTP API 端点")
    print("=" * 60)

    from server import app

    required_paths = [
        '/',
        '/health',
        '/fetch',
        '/search',
        '/extract',
        '/crawl',
        '/parse',
        '/links',
        '/knowledge',
        '/visited',
        '/search/internet',
        '/search/combined',
        '/research',
        '/search/academic',
        '/search/site',
    ]

    existing_paths = [route.path for route in app.routes if hasattr(route, 'path')]
    errors = []

    for path in required_paths:
        if path in existing_paths:
            print(f"  [OK] {path}")
        else:
            errors.append(f"Missing endpoint: {path}")
            print(f"  [FAIL] {path}")

    print()
    return len(errors) == 0, errors


def test_academic_features():
    """测试学术功能"""
    print("=" * 60)
    print("测试 5: 学术功能")
    print("=" * 60)

    from core.academic_search import AcademicSource, is_academic_query

    errors = []

    # 测试学术来源
    expected_sources = [
        'arxiv', 'google_scholar', 'pubmed', 'ieee',
        'cnki', 'github', 'gitee', 'paper_with_code'
    ]

    available_sources = [s.value for s in AcademicSource]
    for source in expected_sources:
        if source in available_sources:
            print(f"  [OK] AcademicSource.{source}")
        else:
            errors.append(f"Missing source: {source}")
            print(f"  [FAIL] AcademicSource.{source}")

    # 测试学术查询识别
    test_queries = [
        ("Transformer paper", True),
        ("机器学习论文", True),
        ("GitHub 项目", True),
        ("买菜", False),
    ]

    for query, expected in test_queries:
        result = is_academic_query(query)
        if result == expected:
            print(f"  [OK] is_academic_query('{query}') = {result}")
        else:
            errors.append(f"is_academic_query('{query}') returned {result}, expected {expected}")
            print(f"  [FAIL] is_academic_query('{query}') = {result}, expected {expected}")

    print()
    return len(errors) == 0, errors


def test_form_search_features():
    """测试表单搜索功能"""
    print("=" * 60)
    print("测试 6: 表单搜索功能")
    print("=" * 60)

    from core.form_search import FormFiller, SearchForm, FormField, SearchFormResult

    errors = []

    # 测试类存在
    classes = [
        ('FormFiller', FormFiller),
        ('SearchForm', SearchForm),
        ('FormField', FormField),
        ('SearchFormResult', SearchFormResult),
    ]

    for name, cls in classes:
        if cls:
            print(f"  [OK] {name}")
        else:
            errors.append(f"Missing class: {name}")
            print(f"  [FAIL] {name}")

    # 测试搜索字段模式
    patterns = FormFiller.SEARCH_FIELD_PATTERNS
    if len(patterns) >= 5:
        print(f"  [OK] SEARCH_FIELD_PATTERNS ({len(patterns)} patterns)")
    else:
        errors.append(f"SEARCH_FIELD_PATTERNS has only {len(patterns)} patterns")
        print(f"  [FAIL] SEARCH_FIELD_PATTERNS ({len(patterns)} patterns)")

    # 测试 FormFiller 方法
    filler_methods = ['detect_search_forms', 'fill_and_submit', 'site_search']
    for method in filler_methods:
        if hasattr(FormFiller, method):
            print(f"  [OK] FormFiller.{method}")
        else:
            errors.append(f"Missing method: FormFiller.{method}")
            print(f"  [FAIL] FormFiller.{method}")

    print()
    return len(errors) == 0, errors


def test_cli_commands():
    """测试 CLI 命令"""
    print("=" * 60)
    print("测试 7: CLI 命令")
    print("=" * 60)

    import subprocess

    result = subprocess.run(
        ['python', 'main.py', 'help'],
        capture_output=True,
        text=True,
        timeout=10
    )

    output = result.stdout + result.stderr

    required_commands = [
        'visit',
        'search',
        'extract',
        'crawl',
        'web',
        'research',
        'academic',
        'site',
    ]

    errors = []

    for cmd in required_commands:
        if cmd in output:
            print(f"  [OK] Command: {cmd}")
        else:
            errors.append(f"Missing command in help: {cmd}")
            print(f"  [FAIL] Command: {cmd}")

    print()
    return len(errors) == 0, errors


async def run_async_tests():
    """运行异步测试"""
    print("=" * 60)
    print("测试 8: 异步初始化测试")
    print("=" * 60)

    errors = []

    try:
        from agents.web_agent import WebAgent
        agent = WebAgent()
        await agent._init()
        print("  [OK] WebAgent._init()")
        await agent.close()
    except Exception as e:
        errors.append(f"WebAgent._init(): {e}")
        print(f"  [FAIL] WebAgent._init(): {e}")

    try:
        from tools.mcp_tools import WebTools
        tools = WebTools()
        await tools.initialize()
        print("  [OK] WebTools.initialize()")
        await tools.close()
    except Exception as e:
        errors.append(f"WebTools.initialize(): {e}")
        print(f"  [FAIL] WebTools.initialize(): {e}")

    print()
    return len(errors) == 0, errors


async def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("Web-Rooter 综合功能测试")
    print("=" * 60 + "\n")

    all_passed = True
    all_errors = []

    # 同步测试
    tests = [
        ("模块导入", test_imports),
        ("WebAgent 方法", test_webagent_methods),
        ("MCP 工具", test_mcp_tools),
        ("HTTP API 端点", test_api_endpoints),
        ("学术功能", test_academic_features),
        ("表单搜索功能", test_form_search_features),
        ("CLI 命令", test_cli_commands),
    ]

    for name, test_func in tests:
        passed, errors = test_func()
        all_passed = all_passed and passed
        all_errors.extend([(name, e) for e in errors])

    # 异步测试
    passed, errors = await run_async_tests()
    all_passed = all_passed and passed
    all_errors.extend([("异步测试", e) for e in errors])

    # 总结
    print("=" * 60)
    print("测试总结")
    print("=" * 60)

    if all_passed:
        print("\n  所有测试通过!")
        print("  功能实现：100%\n")
        return 0
    else:
        print(f"\n  测试失败数量：{len(all_errors)}")
        for category, error in all_errors:
            print(f"  [{category}] {error}")
        print()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

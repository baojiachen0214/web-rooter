"""
学术搜索和填表搜索演示脚本
"""
import asyncio
from core.academic_search import (
    AcademicSource,
    AcademicSearchEngine,
    academic_search,
    code_search,
    is_academic_query,
)
from core.form_search import FormFiller, auto_search
from agents.web_agent import WebAgent


async def demo_academic_search():
    """学术搜索演示"""
    print("=" * 60)
    print("【演示 1】学术搜索：Transformer 架构论文")
    print("=" * 60)

    # 检查是否为学术查询
    query = "Transformer architecture attention"
    print(f"查询：{query}")
    print(f"是否学术查询：{is_academic_query(query)}")
    print()

    # 学术搜索
    engine = AcademicSearchEngine()
    papers = await engine.search_papers(
        query,
        sources=[AcademicSource.ARXIV, AcademicSource.GOOGLE_SCHOLAR],
        num_results=5,
        fetch_abstract=True,
    )
    await engine.close()

    print(f"找到 {len(papers)} 篇论文:\n")
    for i, paper in enumerate(papers, 1):
        print(f"[{i}] {paper.title}")
        print(f"    作者：{', '.join(paper.authors[:3]) if paper.authors else 'N/A'}")
        print(f"    来源：{paper.source}")
        if paper.abstract:
            print(f"    摘要：{paper.abstract[:150]}...")
        if paper.pdf_url:
            print(f"    PDF: {paper.pdf_url}")
        print()


async def demo_code_search():
    """代码项目搜索演示"""
    print("=" * 60)
    print("【演示 2】代码搜索：机器学习框架")
    print("=" * 60)

    engine = AcademicSearchEngine()
    projects = await engine.search_code(
        "machine learning framework",
        sources=[AcademicSource.GITHUB, AcademicSource.GITEE],
        num_results=5,
    )
    await engine.close()

    print(f"找到 {len(projects)} 个项目:\n")
    for i, proj in enumerate(projects, 1):
        print(f"[{i}] {proj.name} ({proj.source})")
        print(f"    语言：{proj.language}")
        print(f"    Stars: {proj.stars}, Forks: {proj.forks}")
        print(f"    {proj.description[:100]}...")
        print(f"    URL: {proj.url}")
        print()


async def demo_agent_academic():
    """Agent 学术搜索演示"""
    print("=" * 60)
    print("【演示 3】Agent 学术搜索：深度学习论文 + 代码")
    print("=" * 60)

    async with WebAgent() as agent:
        result = await agent.search_academic(
            "deep learning neural network",
            include_code=True,
            fetch_abstracts=True,
        )
        print(result.content[:2000])


async def demo_form_search():
    """填表搜索演示"""
    print("=" * 60)
    print("【演示 4】填表搜索：GitHub 站内搜索")
    print("=" * 60)

    # 注意：这个演示需要实际的网站支持
    # 这里展示 API 用法
    print("提示：填表搜索需要实际网站支持")
    print("示例用法:")
    print('  await agent.search_with_form(')
    print('      "https://github.com",')
    print('      "machine learning"')
    print('  )')
    print()

    # 尝试自动搜索（可能需要手动测试）
    try:
        filler = FormFiller()
        # 检测 GitHub 搜索页面
        forms = await filler.detect_search_forms("https://github.com/search")
        print(f"在 GitHub 搜索页面检测到 {len(forms)} 个表单")

        for i, form in enumerate(forms, 1):
            print(f"\n表单 {i}:")
            print(f"  Action: {form.form_action}")
            print(f"  Method: {form.form_method}")
            print(f"  字段:")
            for field in form.fields:
                print(f"    - {field.name} ({field.field_type})")

        await filler.close()
    except Exception as e:
        print(f"演示出错（需要网络连接）: {e}")


async def demo_agent_site_search():
    """Agent 站内搜索演示"""
    print("=" * 60)
    print("【演示 5】Agent 站内搜索")
    print("=" * 60)

    async with WebAgent() as agent:
        # 这个需要实际网站支持
        print("示例用法:")
        print('  await agent.search_with_form(')
        print('      "https://example.com",')
        print('      "search query"')
        print('  )')


async def main():
    """主函数"""
    print("Web-Rooter 学术搜索和填表搜索演示\n")

    demos = {
        "1": demo_academic_search,
        "2": demo_code_search,
        "3": demo_agent_academic,
        "4": demo_form_search,
        "5": demo_agent_site_search,
        "a": lambda: run_all(),
    }

    print("选择演示:")
    print("1. 学术搜索（论文）")
    print("2. 代码项目搜索")
    print("3. Agent 学术搜索")
    print("4. 填表搜索演示")
    print("5. Agent 站内搜索")
    print("a. 运行所有演示")
    print()

    choice = input("请输入选项 (1-5 或 a): ").strip()

    if choice in demos:
        if choice == "a":
            await run_all()
        else:
            await demos[choice]()
    else:
        print("无效选项")


async def run_all():
    """运行所有演示"""
    for demo_func in [demo_academic_search, demo_code_search, demo_agent_academic]:
        try:
            await demo_func()
        except Exception as e:
            print(f"演示出错：{e}")


if __name__ == "__main__":
    asyncio.run(main())

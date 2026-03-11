"""
HTTP 服务器 - 提供 REST API
"""
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import uvicorn
import asyncio

from agents.web_agent import WebAgent
from tools.mcp_tools import WebTools
from config import server_config
from core.search.engine import SearchEngine
from core.academic_search import AcademicSource
from core.version import APP_VERSION

app = FastAPI(title="Web-Rooter API", version=APP_VERSION)

# 全局变量
_web_tools: Optional[WebTools] = None
_agent: Optional[WebAgent] = None


@app.on_event("startup")
async def startup():
    """启动时初始化"""
    global _web_tools, _agent
    _web_tools = WebTools()
    await _web_tools.initialize()
    _agent = WebAgent()
    await _agent._init()
    print(f"[Server] Web-Rooter API 已启动")


@app.on_event("shutdown")
async def shutdown():
    """关闭时清理"""
    global _web_tools, _agent
    if _agent:
        await _agent.close()
    if _web_tools:
        await _web_tools.close()


# ==================== 请求模型 ====================

class FetchRequest(BaseModel):
    url: str
    use_browser: bool = False


class SearchRequest(BaseModel):
    query: str
    url: Optional[str] = None


class ExtractRequest(BaseModel):
    url: str
    target: str


class CrawlRequest(BaseModel):
    start_url: str
    max_pages: int = 10
    max_depth: int = 3


class ParseRequest(BaseModel):
    html: str
    url: Optional[str] = ""


class InternetSearchRequest(BaseModel):
    query: str
    num_results: int = 10
    auto_crawl: bool = True


class ResearchRequest(BaseModel):
    topic: str
    max_pages: int = 10


class AcademicSearchRequest(BaseModel):
    query: str
    num_results: int = 10
    include_code: bool = True
    fetch_abstracts: bool = True


class SiteSearchRequest(BaseModel):
    url: str
    query: str
    use_browser: bool = True


# ==================== API 端点 ====================

@app.get("/")
async def root():
    return {
        "name": "Web-Rooter API",
        "version": APP_VERSION,
        "status": "running"
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.post("/fetch")
async def fetch(request: FetchRequest):
    """获取网页内容"""
    result = await _agent.visit(request.url, use_browser=request.use_browser)
    return result.to_dict()


@app.post("/search")
async def search(request: SearchRequest):
    """搜索信息"""
    result = await _agent.search(request.query, request.url)
    return result.to_dict()


@app.post("/extract")
async def extract(request: ExtractRequest):
    """提取信息"""
    result = await _agent.extract(request.url, request.target)
    return result.to_dict()


@app.post("/crawl")
async def crawl(request: CrawlRequest):
    """爬取网站"""
    result = await _agent.crawl(
        request.start_url,
        request.max_pages,
        request.max_depth
    )
    return result.to_dict()


@app.post("/parse")
async def parse(request: ParseRequest):
    """解析 HTML"""
    result = await _web_tools.parse_html(request.html, request.url)
    return result


@app.get("/links")
async def get_links(url: str, internal_only: bool = True):
    """获取链接"""
    result = await _web_tools.get_links(url, internal_only)
    return result


@app.get("/knowledge")
async def get_knowledge_base():
    """获取知识库"""
    result = await _web_tools.get_knowledge_base()
    return result


@app.get("/visited")
async def get_visited_urls():
    """获取已访问的 URL"""
    urls = _agent.get_visited_urls()
    return {"urls": urls, "count": len(urls)}


@app.post("/search/internet")
async def search_internet(request: InternetSearchRequest):
    """互联网搜索（多引擎）"""
    result = await _agent.search_internet(
        request.query,
        num_results=request.num_results,
        auto_crawl=request.auto_crawl,
    )
    return result.to_dict()


@app.post("/search/combined")
async def search_combined(request: InternetSearchRequest):
    """互联网搜索并爬取内容"""
    result = await _agent.search_internet(
        request.query,
        num_results=request.num_results,
        auto_crawl=request.auto_crawl,
    )
    return result.to_dict()


@app.post("/research")
async def research_topic(request: ResearchRequest):
    """深度研究主题"""
    result = await _agent.research_topic(
        request.topic,
        max_pages=request.max_pages,
    )
    return result.to_dict()


@app.post("/search/academic")
async def search_academic(request: AcademicSearchRequest):
    """学术搜索 - 论文和代码项目"""
    result = await _agent.search_academic(
        request.query,
        num_results=request.num_results,
        include_code=request.include_code,
        fetch_abstracts=request.fetch_abstracts,
    )
    return result.to_dict()


@app.post("/search/site")
async def search_site(request: SiteSearchRequest):
    """站内搜索 - 在网站内部搜索"""
    result = await _agent.search_with_form(
        request.url,
        request.query,
        use_browser=request.use_browser,
    )
    return result.to_dict()


def run_http_server():
    """运行 HTTP 服务器"""
    uvicorn.run(
        app,
        host=server_config.HOST,
        port=server_config.PORT,
        log_level="info"
    )


if __name__ == "__main__":
    run_http_server()

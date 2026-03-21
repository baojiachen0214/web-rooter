# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Web-Rooter MCP Server

构建命令: pyinstaller web-rooter.spec
"""
import sys
from pathlib import Path

block_cipher = None

# 项目根目录
ROOT = Path(SPECPATH)

a = Analysis(
    ['main.py'],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # 搜索引擎配置文件
        (str(ROOT / 'core' / 'engine-config'), 'core/engine-config'),
        # 运行时 profiles 资源
        (str(ROOT / 'profiles' / 'auth'), 'profiles/auth'),
        (str(ROOT / 'profiles' / 'search_templates'), 'profiles/search_templates'),
        (str(ROOT / 'profiles' / 'challenge_profiles'), 'profiles/challenge_profiles'),
        # .env.example 作为参考
        (str(ROOT / '.env.example'), '.'),
    ],
    hiddenimports=[
        # MCP SDK
        'mcp',
        'mcp.server',
        'mcp.server.stdio',
        'mcp.types',
        # Async
        'aiohttp',
        'asyncio',
        # Web parsing
        'beautifulsoup4',
        'bs4',
        'lxml',
        'lxml.html',
        'lxml.etree',
        'html5lib',
        # HTTP
        'requests',
        'requests.adapters',
        # Playwright
        'playwright',
        'playwright.async_api',
        'playwright._impl',
        'playwright._impl._driver',
        # FastAPI (for --server mode)
        'fastapi',
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        # Pydantic
        'pydantic',
        'pydantic.deprecated',
        'pydantic.deprecated.decorator',
        # Others
        'dotenv',
        'rich',
        'rich.console',
        'rich.table',
        'rich.panel',
        # Project modules
        'agents',
        'agents.web_agent',
        'agents.spider',
        'core',
        'core.crawler',
        'core.parser',
        'core.browser',
        'core.browser_bootstrap',
        'core.search',
        'core.search.engine',
        'core.search.engine_base',
        'core.search.engine_config',
        'core.search.advanced',
        'core.search.graph',
        'core.search.universal_parser',
        'core.academic_search',
        'core.citation',
        'core.memory_optimizer',
        'core.element_storage',
        'core.connection_pool',
        'core.session_manager',
        'core.request',
        'core.response',
        'core.scheduler',
        'core.checkpoint',
        'core.result_queue',
        'core.metrics',
        'core.cache',
        'core.search_engine',
        'core.search_engine_base',
        'core.form_search',
        'tools',
        'tools.mcp_tools',
        'config',
        'server',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'unittest',
        'test',
        'tests',
        'pip',
        'setuptools',
        'wheel',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='web-rooter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

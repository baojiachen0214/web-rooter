"""
Playwright 浏览器自动安装模块

在 MCP 服务器启动前检查并自动安装 Playwright Chromium 浏览器。
支持 PyInstaller 打包后的二进制环境。
"""
import subprocess
import sys
import os
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


def _get_playwright_browsers_path() -> Path:
    """获取 Playwright 浏览器安装路径"""
    # 优先使用环境变量
    env_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if env_path:
        return Path(env_path)

    # PyInstaller 打包环境：使用用户目录下的固定路径
    if getattr(sys, 'frozen', False):
        if sys.platform == "win32":
            base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Caches"
        else:
            base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        return base / "web-rooter" / "playwright-browsers"

    # 正常 Python 环境：与 Playwright 默认路径保持一致
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "ms-playwright"


def _build_driver_install_command() -> List[str]:
    """构建 Playwright 驱动安装命令，兼容不同版本返回值。"""
    from playwright._impl._driver import compute_driver_executable

    driver = compute_driver_executable()
    if isinstance(driver, (tuple, list)):
        parts = [str(p) for p in driver if p]
        if len(parts) >= 2:
            # 典型格式: [node_executable, cli_js]
            return [parts[0], parts[1], "install", "chromium"]
        if len(parts) == 1:
            return [parts[0], "install", "chromium"]
    return [str(driver), "install", "chromium"]


def is_chromium_installed() -> bool:
    """检查 Chromium 浏览器是否已安装"""
    browsers_path = _get_playwright_browsers_path()
    if not browsers_path.exists():
        return False

    # 查找 chromium-* 目录
    chromium_dirs = list(browsers_path.glob("chromium-*"))
    if not chromium_dirs:
        return False

    # 检查是否有实际的浏览器可执行文件
    for chromium_dir in chromium_dirs:
        if sys.platform == "win32":
            exe = chromium_dir / "chrome-win" / "chrome.exe"
        elif sys.platform == "darwin":
            exe = chromium_dir / "chrome-mac" / "Chromium.app" / "Contents" / "MacOS" / "Chromium"
        else:
            exe = chromium_dir / "chrome-linux" / "chrome"
        if exe.exists():
            return True

    return False


def install_chromium() -> bool:
    """安装 Playwright Chromium 浏览器"""
    browsers_path = _get_playwright_browsers_path()
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_path)
    # 保证当前进程后续运行也使用同一路径
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_path)

    logger.info(f"正在安装 Chromium 浏览器到 {browsers_path} ...")
    print(f"[Setup] 首次运行，正在安装 Chromium 浏览器...", flush=True)
    print(f"[Setup] 安装路径: {browsers_path}", flush=True)

    try:
        # 方法 1: 通过 Playwright 内部驱动安装（在 PyInstaller 环境中最可靠）
        try:
            command = _build_driver_install_command()
            result = subprocess.run(
                command,
                env=env,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                print("[Setup] Chromium 安装完成!", flush=True)
                logger.info("Chromium 安装成功 (via driver)")
                return True
            logger.warning(f"驱动安装返回 {result.returncode}: {result.stderr}")
        except Exception as e:
            logger.warning(f"Playwright 驱动方式不可用: {e}")

        # 方法 2: python -m playwright（仅在非 frozen 环境中有效）
        if not getattr(sys, 'frozen', False):
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                env=env,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                print("[Setup] Chromium 安装完成!", flush=True)
                logger.info("Chromium 安装成功 (via python -m)")
                return True
            logger.warning(f"python -m playwright 返回 {result.returncode}: {result.stderr}")

        # 方法 3: 查找系统 PATH 中的 playwright 命令
        import shutil
        playwright_bin = shutil.which("playwright")
        if playwright_bin:
            result = subprocess.run(
                [playwright_bin, "install", "chromium"],
                env=env,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                print("[Setup] Chromium 安装完成!", flush=True)
                logger.info("Chromium 安装成功 (via PATH)")
                return True

        print("[Setup] Chromium 安装失败，请手动运行: playwright install chromium", flush=True)
        return False

    except subprocess.TimeoutExpired:
        print("[Setup] 安装超时，请检查网络后手动运行: playwright install chromium", flush=True)
        return False
    except Exception as e:
        logger.error(f"安装异常: {e}")
        print(f"[Setup] 安装出错: {e}", flush=True)
        return False


def ensure_browser_ready() -> bool:
    """
    确保浏览器已就绪。首次运行时自动安装。

    Returns:
        True 如果浏览器已就绪，False 如果安装失败
    """
    # 统一设置环境变量，确保安装与运行路径一致
    browsers_path = _get_playwright_browsers_path()
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_path)

    if is_chromium_installed():
        logger.info("Chromium 浏览器已就绪")
        return True

    logger.info("Chromium 浏览器未安装，开始自动安装...")
    return install_chromium()

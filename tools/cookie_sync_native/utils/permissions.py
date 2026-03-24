"""
macOS 权限管理工具
- 检测完全磁盘访问权限
- 弹出原生授权引导对话框
- 一键打开系统设置
"""

import subprocess
import sys
from pathlib import Path


def has_full_disk_access() -> bool:
    """
    检测当前进程是否有完全磁盘访问权限
    通过尝试读取 Safari Cookie 文件来检测
    """
    test_paths = [
        Path.home() / "Library/Containers/com.apple.Safari/Data/Library/Cookies/Cookies.binarycookies",
        Path.home() / "Library/Cookies/Cookies.binarycookies",
    ]
    
    for path in test_paths:
        if path.exists():
            try:
                with open(path, 'rb') as f:
                    f.read(16)
                return True
            except PermissionError:
                return False
            except Exception:
                continue
    
    # 如果文件不存在，尝试测试其他受保护路径
    test_path = Path.home() / "Library/Mail"
    if test_path.exists():
        try:
            next(test_path.iterdir())
            return True
        except PermissionError:
            return False
    
    return True  # 默认假设有权限


def show_permission_dialog() -> bool:
    """
    显示 macOS 原生弹窗，引导用户授权
    
    Returns:
        True 如果用户点击了"去设置"
    """
    if sys.platform != 'darwin':
        return False
    
    apple_script = '''
    tell application "System Events"
        display dialog "需要完全磁盘访问权限才能读取 Safari Cookie" & return & return & \
            "1. 点击\"去设置\"打开系统设置" & return & \
            "2. 点击左下角锁图标解锁" & return & \
            "3. 添加并勾选 Terminal (或你使用的终端应用)" & return & \
            "4. 返回终端重新运行程序" & return & return & \
            "注意：添加后需要重启终端才能生效" & return & return \
            buttons {"取消", "去设置"} default button "去设置" \
            with icon caution \
            with title "Web-Rooter Cookie 同步工具"
    end tell
    '''
    
    try:
        result = subprocess.run(
            ["osascript", "-e", apple_script],
            capture_output=True,
            text=True,
            timeout=30
        )
        return "去设置" in result.stdout
    except Exception:
        return False


def open_privacy_settings():
    """
    打开系统设置的完全磁盘访问权限页面
    """
    if sys.platform != 'darwin':
        return
    
    try:
        # macOS Ventura (13+) 和 Sonoma (14+)
        subprocess.run([
            "open", "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
        ], check=False, timeout=5)
    except Exception:
        try:
            # 备用方案：直接打开安全性与隐私
            subprocess.run([
                "open", "/System/Library/PreferencePanes/Security.prefPane"
            ], check=False, timeout=5)
        except Exception:
            pass


def request_full_disk_access() -> bool:
    """
    请求完全磁盘访问权限
    
    流程：
    1. 检测是否已有权限
    2. 如果没有，显示引导弹窗
    3. 用户点击"去设置"则打开系统设置
    4. 返回权限状态
    
    Returns:
        True 如果已有权限，False 需要用户去设置授权
    """
    if has_full_disk_access():
        return True
    
    if sys.platform != 'darwin':
        return False
    
    # 显示引导弹窗
    user_wants_settings = show_permission_dialog()
    
    if user_wants_settings:
        open_privacy_settings()
        
        # 再次显示提示，告知用户需要重启终端
        restart_prompt = '''
        tell application "System Events"
            display dialog "系统设置已打开" & return & return & \
                "请完成以下步骤后重启终端：" & return & \
                "1. 添加并勾选你的终端应用" & return & \
                "2. 完全退出当前终端 (Cmd+Q)" & return & \
                "3. 重新打开终端运行程序" \
                buttons {"知道了"} default button "知道了" \
                with icon note \
                with title "授权指引"
        end tell
        '''
        try:
            subprocess.run(
                ["osascript", "-e", restart_prompt],
                capture_output=True,
                timeout=30
            )
        except Exception:
            pass
    
    return False


def check_and_request_safari_access() -> bool:
    """
    专门用于 Safari Cookie 提取的权限检查
    
    Returns:
        True 可以继续提取，False 需要授权
    """
    if has_full_disk_access():
        return True
    
    print("⚠️  需要完全磁盘访问权限才能读取 Safari Cookie")
    print()
    
    if request_full_disk_access():
        # 用户刚授权，再次检查
        return has_full_disk_access()
    
    return False


# ============================================================================
# 替代方案：使用文件选择器获取用户授权
# ============================================================================

def pick_safari_cookie_via_dialog() -> Path:
    """
    使用 macOS 原生文件选择器让用户选择 Cookie 文件
    优点：用户选择文件时会自动获得该文件的访问权限
    
    Returns:
        用户选择的文件路径，如果取消则返回 None
    """
    if sys.platform != 'darwin':
        return None
    
    # 可能的 Cookie 文件位置
    default_locations = [
        str(Path.home() / "Library/Containers/com.apple.Safari/Data/Library/Cookies"),
        str(Path.home() / "Library/Cookies"),
    ]
    
    # 构建 AppleScript，使用 choose file 对话框
    apple_script = f'''
    tell application "System Events"
        set cookiePath to ""
        try
            set cookiePath to choose file with prompt "请选择 Safari Cookie 文件:" & return & \
                "(通常位于 Library/Cookies/Cookies.binarycookies)" \
                default location (path to home folder) \
                of type {{"binarycookies", "public.data"}} \
                with invisibles
            return POSIX path of cookiePath
        on error
            return "CANCELLED"
        end try
    end tell
    '''
    
    try:
        result = subprocess.run(
            ["osascript", "-e", apple_script],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        path_str = result.stdout.strip()
        
        if path_str == "CANCELLED" or not path_str:
            return None
        
        path = Path(path_str)
        if path.exists() and "Cookies.binarycookies" in str(path):
            return path
        
        # 用户可能选择了错误的文件，给提示
        subprocess.run([
            "osascript", "-e",
            '''display dialog "选择的文件可能不是 Safari Cookie 文件" & return & \
                "正确路径通常是：" & return & \
                "~/Library/Cookies/Cookies.binarycookies" \
                buttons {"知道了"} with icon caution'''
        ], capture_output=True, timeout=10)
        
        return None
        
    except Exception as e:
        print(f"文件选择器出错: {e}")
        return None


def try_extract_with_file_picker(domain_filter=None):
    """
    尝试使用文件选择器方式提取 Safari Cookie
    适用于没有 Full Disk Access 但用户愿意手动选择文件的情况
    
    Returns:
        (cookies_dict, success)
    """
    print("ℹ️  尝试通过文件选择器获取 Cookie...")
    print("   (选择文件时会自动获得该文件的访问权限)")
    print()
    
    cookie_path = pick_safari_cookie_via_dialog()
    
    if not cookie_path:
        return {}, False
    
    try:
        from browsers.safari import SafariCookieExtractor
        extractor = SafariCookieExtractor(str(cookie_path))
        cookies = extractor.extract_cookies(domain_filter)
        return {"Safari": cookies}, True
    except Exception as e:
        print(f"✗ 提取失败: {e}")
        return {}, False

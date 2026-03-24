#!/usr/bin/env python3
"""
Web-Rooter Cookie 同步工具 - 原生 Python 版本
无需外部二进制文件，直接提取浏览器 Cookie

使用方法:
    python main.py                           # 提取所有浏览器
    python main.py --browser chrome          # 只提取 Chrome
    python main.py --domain zhihu.com        # 只提取指定域名
    python main.py --output ./cookies.json   # 指定输出路径
"""

import argparse
import sys
from pathlib import Path

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))


def main():
    parser = argparse.ArgumentParser(
        description="从本地浏览器提取 Cookie 并导出为 Web-Rooter 格式",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 提取所有浏览器 Cookie
  python main.py
  
  # 只提取 Chrome
  python main.py --browser chrome
  
  # 只提取指定域名
  python main.py --domain zhihu.com
  
  # 指定输出路径
  python main.py --output ~/.web-rooter/login_profiles.json
  
  # 列出支持的浏览器
  python main.py --list
        """
    )
    
    parser.add_argument(
        "--browser", "-b",
        help="只提取指定浏览器 (chrome, edge, firefox, brave, opera, vivaldi, chromium, safari)"
    )
    
    parser.add_argument(
        "--domain", "-d",
        help="只提取包含此域名的 Cookie"
    )
    
    parser.add_argument(
        "--output", "-o",
        help="输出文件路径 (默认: .web-rooter/login_profiles.json)"
    )
    
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="列出支持的浏览器"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="详细输出"
    )
    
    parser.add_argument(
        "--check-permissions",
        action="store_true",
        help="检查并申请必要的权限 (macOS Safari 需要)"
    )
    
    args = parser.parse_args()
    
    # 检查权限（macOS Safari 专用）
    if args.check_permissions:
        if sys.platform != 'darwin':
            print("✓ 当前不是 macOS，无需特殊权限")
            return 0
        
        from utils.permissions import check_and_request_safari_access, has_full_disk_access
        
        print("=" * 60)
        print("权限检查")
        print("=" * 60)
        print()
        
        if has_full_disk_access():
            print("✓ 已有完全磁盘访问权限")
            print("  可以正常提取 Safari Cookie")
            return 0
        else:
            print("✗ 没有完全磁盘访问权限")
            print("  Safari Cookie 提取需要此权限")
            print()
            
            if check_and_request_safari_access():
                print()
                print("✓ 权限申请已处理")
                print("  请重启终端后重新运行程序")
            return 0
    
    # 列出支持的浏览器
    if args.list:
        from browsers.paths import get_browser_paths
        
        print("支持的浏览器:")
        print()
        
        paths = get_browser_paths()
        for name, config in paths.items():
            cookie_file = Path(config.cookie_file)
            exists = "✓" if cookie_file.exists() else "✗"
            print(f"  {exists} {config.name}")
            if args.verbose:
                print(f"     路径: {config.cookie_file}")
                print()
        

        # Safari 特殊处理 (macOS 专属)
        if sys.platform == 'darwin':
            from browsers.safari import SAFARI_COOKIE_PATH
            safari_exists = "✓" if SAFARI_COOKIE_PATH.exists() else "✗"
            print(f"  {safari_exists} Safari")
            if args.verbose:
                print(f"     路径：{SAFARI_COOKIE_PATH}")
        elif args.verbose:
            print(f"  ✗ Safari (仅 macOS 支持)")

        # Firefox 特殊处理
        from browsers.paths import find_firefox_profiles
        firefox_profiles = find_firefox_profiles()
        if firefox_profiles:
            print(f"  ✓ Firefox ({len(firefox_profiles)} 个配置文件)")
            if args.verbose:
                for profile in firefox_profiles:
                    print(f"     - {profile['name']}")
        else:
            print("  ✗ Firefox (未找到配置文件)")
        
        return 0
    
    # 检查依赖
    try:
        import cryptography
    except ImportError:
        print("错误: 缺少依赖 'cryptography'")
        print()
        print("请安装依赖:")
        print("  pip install cryptography")
        return 1
    
    # 提取 Cookie
    print("=" * 60)
    print("Web-Rooter Cookie 同步工具")
    print("=" * 60)
    print()
    
    all_cookies = {}
    
    if args.browser:
        # 只提取指定浏览器
        from browsers.paths import get_browser_paths
        
        browser_name = args.browser.lower()
        paths = get_browser_paths()
        
        # Safari 特殊处理（不在 paths 中）
        if browser_name == "safari":
            if sys.platform != 'darwin':
                print(f"错误：Safari 仅支持 macOS")
                return 1
            from browsers.safari import extract_all_safari_cookies
            safari_cookies = extract_all_safari_cookies(args.domain)
            all_cookies.update(safari_cookies)
        elif browser_name not in paths:
            print(f"错误: 不支持的浏览器 '{args.browser}'")
            print(f"错误：不支持的浏览器 '{args.browser}'")
            print(f"支持的浏览器：{', '.join(paths.keys())}, safari")
            return 1
        else:
        
            config = paths[browser_name]
            
            try:
                if config.is_chromium:
                    from browsers.chromium import ChromiumCookieExtractor
                    extractor = ChromiumCookieExtractor(browser_name)
                    cookies = extractor.extract_cookies(args.domain)
                    all_cookies[config.name] = cookies
                else:
                    from browsers.firefox import extract_all_firefox_cookies
                    firefox_cookies = extract_all_firefox_cookies(args.domain)
                    all_cookies.update(firefox_cookies)
            except Exception as e:
                print(f"✗ {config.name}: {e}")
            return 1
    else:
        # 提取所有浏览器
        from browsers.chromium import extract_all_chromium_cookies
        from browsers.firefox import extract_all_firefox_cookies

        print("正在提取 Chromium 系列浏览器...")
        chromium_cookies = extract_all_chromium_cookies(args.domain)
        all_cookies.update(chromium_cookies)

        print()
        print("正在提取 Firefox...")
        firefox_cookies = extract_all_firefox_cookies(args.domain)
        all_cookies.update(firefox_cookies)

        # Safari (仅 macOS)
        if sys.platform == 'darwin':
            print()
            print("正在提取 Safari...")
            from browsers.safari import extract_all_safari_cookies
            safari_cookies = extract_all_safari_cookies(args.domain)
            all_cookies.update(safari_cookies)
    
    # 打印摘要
    from exporter import print_summary
    print_summary(all_cookies)
    
    # 导出
    if all_cookies:
        from exporter import export_to_web_rooter
        
        output_path = export_to_web_rooter(all_cookies, args.output)
        print()
        print(f"✓ 已导出到: {output_path}")
        
        # 统计
        total = sum(len(cookies) for cookies in all_cookies.values())
        print(f"  总计: {total} 个 Cookie")
    else:
        print()
        print("✗ 未提取到任何 Cookie")
        return 1
    
    print()
    print("提示: Cookie 已准备好供 Web-Rooter 使用")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

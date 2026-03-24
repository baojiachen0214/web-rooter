#!/usr/bin/env python3
"""
权限检查与授权工具 (macOS)
快速检查并申请 Safari Cookie 提取所需的权限
"""

import sys

if sys.platform != 'darwin':
    print("此工具仅适用于 macOS")
    sys.exit(0)

from utils.permissions import (
    has_full_disk_access,
    check_and_request_safari_access,
    try_extract_with_file_picker
)


def main():
    print("=" * 60)
    print("Web-Rooter Cookie 同步工具 - 权限检查")
    print("=" * 60)
    print()
    
    # 检查当前权限状态
    if has_full_disk_access():
        print("✅ 已有完全磁盘访问权限")
        print("   可以正常提取 Safari Cookie")
        print()
        print("提示：如果仍然无法提取，请尝试：")
        print("  1. 完全退出终端 (Cmd+Q)")
        print("  2. 重新打开终端")
        return 0
    
    print("❌ 没有完全磁盘访问权限")
    print()
    print("说明：")
    print("  Safari 的 Cookie 文件位于受保护的沙盒容器中，")
    print("  需要\"完全磁盘访问权限\"才能读取。")
    print()
    
    # 提供选项
    print("请选择操作：")
    print()
    print("  [1] 打开系统设置，手动授权 (推荐)")
    print("      优点：一次授权，永久有效")
    print("      缺点：需要重启终端")
    print()
    print("  [2] 使用文件选择器临时授权")
    print("      优点：无需修改系统设置")
    print("      缺点：每次都需要手动选择文件")
    print()
    print("  [3] 取消")
    print()
    
    choice = input("请输入选项 (1/2/3): ").strip()
    
    if choice == '1':
        print()
        check_and_request_safari_access()
        
    elif choice == '2':
        print()
        print("ℹ️  将打开文件选择器...")
        result, success = try_extract_with_file_picker()
        
        if success:
            total = len(result.get("Safari", []))
            print()
            print(f"✅ 成功提取 {total} 个 Safari Cookie")
            print("   (这些 Cookie 已可通过正常流程导出)")
        else:
            print()
            print("❌ 未能提取 Cookie")
            
    else:
        print()
        print("已取消")
        print()
        print("如需稍后授权，可以运行：")
        print("  python check_permissions.py")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

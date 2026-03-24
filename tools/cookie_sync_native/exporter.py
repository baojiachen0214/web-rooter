"""
Cookie 导出器 - 转换为 Web-Rooter 格式
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any


# 预定义的域名映射
DOMAIN_PROFILES = {
    "zhihu.com": {
        "name": "zhihu_auto_auth",
        "priority": 220,
        "login_url": "https://www.zhihu.com/signin",
    },
    "xiaohongshu.com": {
        "name": "xiaohongshu_auto_auth",
        "priority": 220,
        "login_url": "https://www.xiaohongshu.com/explore",
    },
    "xhslink.com": {
        "name": "xiaohongshu_auto_auth",
        "priority": 220,
        "login_url": "https://www.xiaohongshu.com/explore",
    },
    "bilibili.com": {
        "name": "bilibili_auto_auth",
        "priority": 220,
        "login_url": "https://www.bilibili.com",
    },
    "weibo.com": {
        "name": "weibo_auto_auth",
        "priority": 220,
        "login_url": "https://weibo.com/login.php",
    },
    "weibo.cn": {
        "name": "weibo_auto_auth",
        "priority": 220,
        "login_url": "https://weibo.com/login.php",
    },
    "douyin.com": {
        "name": "douyin_auto_auth",
        "priority": 220,
        "login_url": "https://www.douyin.com",
    },
    "iesdouyin.com": {
        "name": "douyin_auto_auth",
        "priority": 220,
        "login_url": "https://www.douyin.com",
    },
    "taobao.com": {
        "name": "taobao_auto_auth",
        "priority": 210,
        "login_url": "https://www.taobao.com",
    },
    "tmall.com": {
        "name": "tmall_auto_auth",
        "priority": 210,
        "login_url": "https://www.tmall.com",
    },
    "jd.com": {
        "name": "jd_auto_auth",
        "priority": 210,
        "login_url": "https://www.jd.com",
    },
    "baidu.com": {
        "name": "baidu_auto_auth",
        "priority": 200,
        "login_url": "https://www.baidu.com",
    },
    "google.com": {
        "name": "google_auto_auth",
        "priority": 200,
        "login_url": "https://www.google.com",
    },
    "github.com": {
        "name": "github_auto_auth",
        "priority": 200,
        "login_url": "https://github.com/login",
    },
}


def convert_cookie_to_web_rooter(cookie: Dict[str, Any]) -> Dict[str, Any]:
    """
    将内部 Cookie 格式转换为 Web-Rooter 格式
    """
    result = {
        "name": cookie["name"],
        "value": cookie["value"],
        "domain": cookie.get("domain", cookie.get("host", "")),
        "path": cookie.get("path", "/"),
        "secure": cookie.get("secure", False),
        "httpOnly": cookie.get("http_only", False),
    }
    
    # 处理过期时间
    if cookie.get("expires"):
        try:
            # 如果是 ISO 格式字符串，转换为时间戳
            if isinstance(cookie["expires"], str):
                from datetime import datetime
                dt = datetime.fromisoformat(cookie["expires"].replace('Z', '+00:00'))
                result["expires"] = dt.timestamp()
        except:
            pass
    
    # 处理 sameSite
    if cookie.get("same_site"):
        result["sameSite"] = cookie["same_site"]
    
    return result


def domain_matches(domain: str, pattern: str) -> bool:
    """
    严格域名匹配

    防止错误匹配 (如 phishing-github.com 匹配到 github.com)
    """
    domain = domain.lstrip(".").lower()
    pattern = pattern.lstrip(".").lower()
    return domain == pattern or domain.endswith("." + pattern)


def group_cookies_by_domain(cookies: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """按域名分组 Cookie（自动去重）"""
    groups = {}

    for cookie in cookies:
        domain = cookie.get("domain") or cookie.get("host", "")

        # 标准化域名（移除开头的点）
        domain = domain.lstrip(".")

        if domain not in groups:
            groups[domain] = []

        # 去重：按 (name, path) 三元组
        cookie_key = (cookie.get("name", ""), cookie.get("path", "/"))
        existing_keys = {(c.get("name", ""), c.get("path", "/")): i for i, c in enumerate(groups[domain])}

        if cookie_key in existing_keys:
            # 已存在，保留过期时间更新的
            existing_idx = existing_keys[cookie_key]
            existing_cookie = groups[domain][existing_idx]

            # 比较过期时间，保留更新的
            try:
                new_expires = cookie.get("expires")
                existing_expires = existing_cookie.get("expires")

                if new_expires and existing_expires:
                    # 都是 ISO 字符串，直接比较
                    if new_expires > existing_expires:
                        groups[domain][existing_idx] = cookie
            except:
                pass  # 无法比较时保留现有的
        else:
            groups[domain].append(cookie)

    return groups


def create_web_rooter_profile(domain: str, cookies: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    创建 Web-Rooter profile
    """
    # 查找预配置
    profile_config = None
    for key, config in DOMAIN_PROFILES.items():
        if domain_matches(domain, key):
            profile_config = config
            break
    
    if profile_config:
        return {
            "name": profile_config["name"],
            "enabled": True,
            "priority": profile_config["priority"],
            "domains": [domain],
            "mode": "cookies",
            "login_url": profile_config["login_url"],
            "headers": {},
            "cookies": [convert_cookie_to_web_rooter(c) for c in cookies],
            "local_storage": {},
            "notes": f"Auto-extracted cookies for {domain}",
        }
    else:
        # 自动生成
        return {
            "name": f"{domain.replace('.', '_')}_auto_auth",
            "enabled": True,
            "priority": 200,
            "domains": [domain],
            "mode": "cookies",
            "login_url": f"https://{domain}",
            "headers": {},
            "cookies": [convert_cookie_to_web_rooter(c) for c in cookies],
            "local_storage": {},
            "notes": f"Auto-extracted cookies for {domain}",
        }


def export_to_web_rooter(
    all_cookies: Dict[str, List[Dict[str, Any]]],
    output_path: str = None
) -> str:
    """
    导出为 Web-Rooter 格式
    
    Args:
        all_cookies: {浏览器名称: Cookie列表}
        output_path: 输出文件路径，None 则使用默认位置
        
    Returns:
        输出文件路径
    """
    # 收集所有 Cookie
    all_cookies_flat = []
    for browser_name, cookies in all_cookies.items():
        for cookie in cookies:
            cookie["_source"] = browser_name
            all_cookies_flat.append(cookie)

    # 验证：检查是否有 Cookie
    if not all_cookies_flat:
        print("[WARNING] 没有提取到任何 Cookie")
        return ""

    # 按域名分组
    domain_groups = group_cookies_by_domain(all_cookies_flat)

    # 验证：检查是否有有效域名
    if not domain_groups:
        print("[WARNING] 没有有效的 Cookie 域名")
        return ""
    
    # 创建 profiles
    profiles = []
    for domain, cookies in domain_groups.items():
        if cookies:  # 只添加有 Cookie 的域名
            profile = create_web_rooter_profile(domain, cookies)
            profiles.append(profile)
    
    # 构建输出
    output_data = {
        "version": 1,
        "generated_at": datetime.now().isoformat(),
        "profiles": profiles,
    }
    
    # 确定输出路径
    if output_path is None:
        # 优先使用项目目录
        project_dir = Path(__file__).parent
        local_config = project_dir / ".web-rooter" / "login_profiles.json"
        
        if (project_dir.parent / ".web-rooter").exists():
            local_config = project_dir.parent / ".web-rooter" / "login_profiles.json"
        
        local_config.parent.mkdir(parents=True, exist_ok=True)
        output_path = str(local_config)
    
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # 备份现有文件
    if output_file.exists():
        backup_path = output_file.with_suffix(".json.bak")
        backup_path.write_text(output_file.read_text(), encoding='utf-8')
    
    # 写入文件
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    # 设置权限
    import os
    os.chmod(output_file, 0o600)
    
    return str(output_file)


def print_summary(all_cookies: Dict[str, List[Dict[str, Any]]]):
    """打印提取摘要"""
    print()
    print("=" * 60)
    print("提取摘要")
    print("=" * 60)
    
    total_cookies = 0
    for browser_name, cookies in all_cookies.items():
        count = len(cookies)
        total_cookies += count
        print(f"  {browser_name}: {count} 个 Cookie")
    
    # 按域名统计
    all_cookies_flat = []
    for cookies in all_cookies.values():
        all_cookies_flat.extend(cookies)
    
    domain_groups = group_cookies_by_domain(all_cookies_flat)
    
    print()
    print(f"  总计: {total_cookies} 个 Cookie")
    print(f"  涉及域名: {len(domain_groups)} 个")
    print()
    
    if domain_groups:
        print("  域名列表:")
        for domain in sorted(domain_groups.keys())[:10]:  # 只显示前10个
            count = len(domain_groups[domain])
            print(f"    - {domain}: {count} 个 Cookie")
        
        if len(domain_groups) > 10:
            print(f"    ... 还有 {len(domain_groups) - 10} 个域名")
    
    print("=" * 60)

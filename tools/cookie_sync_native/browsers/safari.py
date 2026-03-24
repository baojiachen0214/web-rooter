"""
Safari Cookie 提取（macOS 专属）
支持解析 Safari 的 .binarycookies 文件

参考：
- temp/binary-cookies-parser-main/src/parsers/binary.ts
- https://github.com/xaitax/Chrome-App-Bound-Encryption-Decryption
"""

import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional


# macOS Cookie 文件路径（按优先级排序）
SAFARI_COOKIE_PATHS = [
    # 现代 macOS (Safari 沙盒化)
    Path.home() / "Library/Containers/com.apple.Safari/Data/Library/Cookies/Cookies.binarycookies",
    # 旧版 macOS
    Path.home() / "Library/Cookies/Cookies.binarycookies",
]

# Mac Epoch 偏移（1970-01-01 到 2001-01-01 的秒数）
MAC_EPOCH_OFFSET = 978307200


def find_safari_cookie_file() -> Optional[Path]:
    """查找 Safari Cookie 文件（返回第一个可读取的路径）"""
    for path in SAFARI_COOKIE_PATHS:
        if path.exists():
            # 检查是否可读
            try:
                with open(path, 'rb') as f:
                    f.read(4)  # 尝试读取文件头
                return path
            except PermissionError:
                continue
            except Exception:
                continue
    return None


class SafariCookieExtractor:
    """Safari Cookie 提取器"""

    def __init__(self, cookie_file: Optional[str] = None):
        """
        Args:
            cookie_file: 指定 Cookie 文件路径，None 则使用默认路径
        """
        if cookie_file:
            self.cookie_file = Path(cookie_file)
        else:
            # 自动查找可用的 Cookie 文件
            found_path = find_safari_cookie_file()
            if found_path is None:
                raise FileNotFoundError(
                    "未找到可读取的 Safari Cookie 文件。\n"
                    "这通常是因为 macOS 的隐私保护机制（TCC）限制了访问。\n\n"
                    "解决方案：\n"
                    "1. 打开 系统设置 → 隐私与安全性 → 完全磁盘访问权限\n"
                    "2. 添加 Terminal（或你正在使用的终端应用）\n"
                    "3. 重启终端后再次尝试\n\n"
                    f"尝试的路径：\n  - {'\n  - '.join(str(p) for p in SAFARI_COOKIE_PATHS)}"
                )
            self.cookie_file = found_path

    def extract_cookies(self, domain_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        提取所有 Cookie

        Args:
            domain_filter: 只返回包含此字符串的域名的 Cookie

        Returns:
            Cookie 列表
        """
        if not self.cookie_file.exists():
            raise FileNotFoundError(f"未找到 Safari Cookie 文件：{self.cookie_file}")

        with open(self.cookie_file, 'rb') as f:
            data = f.read()

        return self._parse_binary_cookies(data, domain_filter)

    def _parse_binary_cookies(self, data: bytes, domain_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        解析二进制 Cookie 数据

        文件格式：
        - 文件头：cook (4 字节) + numPages (4 字节，大端) + pageSizes (numPages * 4 字节，大端)
        - 每页：pageHeader (4 字节，固定 256) + numCookies (4 字节，小端) + cookieOffsets (numCookies * 4 字节)
        - 每个 Cookie：cookieSize + flags + 未知字段 + 字符串偏移表 + expiration/creation 时间戳
        """
        cookies = []

        if len(data) < 4:
            raise ValueError("数据过短，不是有效的 binarycookies 文件")

        # 验证文件头
        header = data[0:4].decode('ascii', errors='ignore')
        if header != 'cook':
            raise ValueError("无效的文件头：期望 'cook'，得到 '{}'".format(header))

        position = 4

        # 读取页数（大端）
        if len(data) < position + 4:
            raise ValueError("数据过短，无法读取页数")
        num_pages = struct.unpack('>I', data[position:position + 4])[0]
        position += 4

        # 读取每页大小（大端）
        page_sizes = []
        for _ in range(num_pages):
            if len(data) < position + 4:
                raise ValueError("数据过短，无法读取页大小")
            page_size = struct.unpack('>I', data[position:position + 4])[0]
            page_sizes.append(page_size)
            position += 4

        # 解析每页
        for page_idx, page_size in enumerate(page_sizes):
            if len(data) < position + page_size:
                raise ValueError(f"页 {page_idx} 数据不完整")

            page_data = data[position:position + page_size]
            page_cookies = self._parse_page(page_data, page_idx, domain_filter)
            cookies.extend(page_cookies)
            position += page_size

        return cookies

    def _parse_page(self, page_data: bytes, page_idx: int, domain_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        解析单个页面

        页面格式：
        - pageHeader (4 字节，固定 256，大端)
        - numCookies (4 字节，小端)
        - cookieOffsets (numCookies * 4 字节，小端)
        """
        cookies = []

        if len(page_data) < 4:
            raise ValueError(f"页 {page_idx} 数据过短")

        # 验证页头
        page_header = struct.unpack('>I', page_data[0:4])[0]
        if page_header != 256:
            raise ValueError(f"页 {page_idx} 无效的页头：期望 256，得到 {page_header}")

        # 读取 Cookie 数量（小端）
        if len(page_data) < 8:
            raise ValueError(f"页 {page_idx} 数据过短")
        num_cookies = struct.unpack('<I', page_data[4:8])[0]

        # 读取 Cookie 偏移量（小端）
        offsets = []
        offset_start = 8
        for i in range(num_cookies):
            offset_pos = offset_start + i * 4
            if len(page_data) < offset_pos + 4:
                raise ValueError(f"页 {page_idx} Cookie {i} 偏移量读取失败")
            offset = struct.unpack('<I', page_data[offset_pos:offset_pos + 4])[0]
            offsets.append(offset)

        # 解析每个 Cookie
        for i, offset in enumerate(offsets):
            try:
                cookie = self._parse_cookie(page_data, offset, page_idx, i)
                if cookie:
                    # 域名过滤
                    if domain_filter is None or domain_filter.lower() in cookie.get('domain', '').lower():
                        cookies.append(cookie)
            except Exception as e:
                # 单个 Cookie 解析失败不影响其他 Cookie
                continue

        return cookies

    def _parse_cookie(self, page_data: bytes, offset: int, page_idx: int, cookie_idx: int) -> Optional[Dict[str, Any]]:
        """
        解析单个 Cookie 数据

        Cookie 格式：
        - cookieSize (4 字节，小端)
        - flags (4 字节，小端) - 1=secure, 4=httpOnly
        - 未知字段 (8 字节)
        - 字符串偏移表 (4 个偏移量，每个 4 字节)：url, name, path, value
        - 未知字段 (4 字节)
        - expiration (8 字节，double，Mac Epoch)
        - creation (8 字节，double，Mac Epoch)
        """
        if offset >= len(page_data):
            return None

        # 读取 Cookie 大小
        if offset + 4 > len(page_data):
            return None
        cookie_size = struct.unpack('<I', page_data[offset:offset + 4])[0]

        if cookie_size == 0 or offset + cookie_size > len(page_data):
            return None

        cookie_data = page_data[offset:offset + cookie_size]

        # 读取 flags (偏移 4)
        if len(cookie_data) < 8:
            return None
        flags = struct.unpack('<I', cookie_data[4:8])[0]

        # 读取字符串偏移表 (从偏移 16 开始，4 个偏移量)
        if len(cookie_data) < 32:
            return None

        url_offset = struct.unpack('<I', cookie_data[16:20])[0]
        name_offset = struct.unpack('<I', cookie_data[20:24])[0]
        path_offset = struct.unpack('<I', cookie_data[24:28])[0]
        value_offset = struct.unpack('<I', cookie_data[28:32])[0]

        # 读取过期时间 (偏移 40，8 字节 double)
        if len(cookie_data) < 48:
            return None
        expiration_ts = struct.unpack('<d', cookie_data[40:48])[0] + MAC_EPOCH_OFFSET
        expiration = datetime.fromtimestamp(expiration_ts, tz=timezone.utc)

        # 读取创建时间 (偏移 48，8 字节 double)
        if len(cookie_data) < 56:
            return None
        creation_ts = struct.unpack('<d', cookie_data[48:56])[0] + MAC_EPOCH_OFFSET
        creation = datetime.fromtimestamp(creation_ts, tz=timezone.utc)

        # 读取字符串（以 null 结尾）
        url = self._read_null_terminated_string(cookie_data, url_offset)
        name = self._read_null_terminated_string(cookie_data, name_offset)
        path = self._read_null_terminated_string(cookie_data, path_offset)
        value = self._read_null_terminated_string(cookie_data, value_offset)

        # 转换为标准格式
        return {
            "host": url,
            "domain": url,
            "name": name,
            "value": value,
            "path": path,
            "expires": expiration.isoformat() if expiration else None,
            "creation": creation.isoformat() if creation else None,
            "secure": bool(flags & 1),
            "http_only": bool(flags & 4),
            "same_site": None,  # Safari binarycookies 不包含 sameSite 信息
        }

    def _read_null_terminated_string(self, data: bytes, offset: int) -> str:
        """读取 null 结尾的字符串"""
        if offset >= len(data) or offset < 0:
            return ""

        end = offset
        while end < len(data) and data[end] != 0:
            end += 1

        try:
            return data[offset:end].decode('utf-8', errors='replace').strip()
        except Exception:
            return ""


def extract_all_safari_cookies(domain_filter: Optional[str] = None) -> Dict[str, List[Dict]]:
    """
    从 Safari 提取 Cookie

    Returns:
        {浏览器名称：Cookie 列表}
    """
    import sys
    results = {}

    # 查找可用的 Cookie 文件
    cookie_file = find_safari_cookie_file()

    if cookie_file is None:
        # macOS 特有的权限处理
        if sys.platform == 'darwin':
            # 尝试使用权限管理工具引导用户
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent))
                from utils.permissions import check_and_request_safari_access, try_extract_with_file_picker
                
                # 方案1：尝试弹出授权引导
                if check_and_request_safari_access():
                    # 用户授权后再次尝试
                    cookie_file = find_safari_cookie_file()
                    if cookie_file is None:
                        return results
                else:
                    # 方案2：使用文件选择器作为备选
                    print()
                    print("💡 提示：你也可以通过文件选择器手动选择 Cookie 文件")
                    user_input = input("   是否使用文件选择器? (y/n): ").strip().lower()
                    
                    if user_input in ('y', 'yes'):
                        return try_extract_with_file_picker(domain_filter)
                    else:
                        print()
                        print("✗ Safari: 跳过提取")
                        print("   如需授权，请运行：")
                        print("   python -c \"from utils.permissions import request_full_disk_access; request_full_disk_access()\"")
                        return results
                        
            except ImportError:
                pass
            except Exception as e:
                # 静默处理权限工具的错误，回退到原始提示
                pass
        
        # 回退：原始文字提示
        if cookie_file is None:
            print(f"✗ Safari: 无法访问 Cookie 文件（权限不足）")
            print(f"  请授予终端完全磁盘访问权限：")
            print(f"  系统设置 → 隐私与安全性 → 完全磁盘访问权限 → 添加 Terminal")
            return results

    try:
        extractor = SafariCookieExtractor(str(cookie_file))
        cookies = extractor.extract_cookies(domain_filter)
        results["Safari"] = cookies
        if cookies:
            print(f"✓ Safari: 提取了 {len(cookies)} 个 Cookie")
        else:
            print(f"✓ Safari: 未找到匹配 '{domain_filter}' 的 Cookie")
    except Exception as e:
        print(f"✗ Safari: {e}")

    return results

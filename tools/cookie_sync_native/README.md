# Web-Rooter Cookie 同步工具 - 原生 Python 版本

无需外部二进制文件，直接使用 Python 从浏览器提取 Cookie。

## 特性

- ✅ **纯 Python 实现** - 无需下载/管理外部二进制文件
- ✅ **跨平台** - 支持 macOS、Windows、Linux
- ✅ **自动解密** - 支持 Chromium 的 AES 加密
- ✅ **多浏览器** - Chrome、Edge、Brave、Opera、Firefox、Safari
- ✅ **Web-Rooter 格式** - 直接生成可用的配置文件

## 系统要求

- Python 3.10+
- `cryptography` 库

## 安装

```bash
cd tools/cookie_sync_native

# 安装依赖
pip install -r requirements.txt
```

## 使用方法

### 快速开始

```bash
# 提取所有浏览器 Cookie
python main.py

# 输出示例:
# ============================================================
# Web-Rooter Cookie 同步工具
# ============================================================
#
# 正在提取 Chromium 系列浏览器...
# ✓ Chrome: 提取了 125 个 Cookie
# ✓ Edge: 提取了 45 个 Cookie
# ✓ Brave: 提取了 32 个 Cookie
#
# 正在提取 Firefox...
# ✓ Firefox (default): 提取了 89 个 Cookie
#
# ============================================================
# 提取摘要
# ============================================================
#   Chrome: 125 个 Cookie
#   Edge: 45 个 Cookie
#   Brave: 32 个 Cookie
#   Firefox (default): 89 个 Cookie
#
#   总计: 291 个 Cookie
#   涉及域名: 18 个
#
# ============================================================
#
# ✓ 已导出到: .web-rooter/login_profiles.json
#   总计: 291 个 Cookie
```

### 命令选项

```bash
# 只提取指定浏览器
python main.py --browser chrome

# 只提取指定域名
python main.py --domain zhihu.com

# 指定输出路径
python main.py --output ~/.web-rooter/login_profiles.json

# 列出支持的浏览器
python main.py --list

# 详细输出
python main.py --list --verbose
```

## 支持的浏览器

| 浏览器 | macOS | Windows | Linux |
|--------|-------|---------|-------|
| Chrome | ✅ | ✅ | ✅ |
| Edge | ✅ | ✅ | ✅ |
| Brave | ✅ | ✅ | ✅ |
| Opera | ✅ | ✅ | ✅ |
| Opera GX | ✅ | ❌ | ❌ |
| Vivaldi | ✅ | ✅ | ✅ |
| Chromium | ✅ | ✅ | ✅ |
| Firefox | ✅ | ✅ | ✅ |
| Safari | ✅ | ❌ | ❌ |

## 工作原理

### Chromium 系列 (Chrome, Edge, Brave 等)

**macOS:**
1. 从 Keychain 获取 `Chrome Safe Storage` 密码
2. 使用 PBKDF2 (salt="saltysalt", iter=1003) 派生 AES 密钥
3. 使用 AES-CBC 解密 Cookie 值

**Windows:**
1. 从 `Local State` 文件读取 `os_crypt.encrypted_key`
2. 使用 DPAPI (CryptUnprotectData) 解密主密钥
3. 使用 AES-GCM 解密 Cookie 值

**Linux:**
1. 从 Secret Service (D-Bus) 或默认密码 "peanuts" 获取
2. 使用 PBKDF2 (salt="saltysalt", iter=1) 派生 AES 密钥
3. 使用 AES-CBC 解密 Cookie 值

### Firefox

Firefox 的 Cookie 通常**未加密**（明文存储在 SQLite 数据库中），所以直接读取即可。

## 项目结构

```
cookie_sync_native/
├── main.py                    # 主入口
├── exporter.py                # Web-Rooter 格式导出
├── requirements.txt           # 依赖
├── README.md                  # 本文档
├── core/                      # 核心加密模块
│   ├── crypto.py             # AES/3DES/PBKDF2
│   ├── dpapi.py              # Windows DPAPI
│   ├── keychain.py           # macOS Keychain
│   └── secret_service.py     # Linux Secret Service
└── browsers/                  # 浏览器实现
    ├── paths.py              # 浏览器路径配置
    ├── chromium.py           # Chromium Cookie 提取
    └── firefox.py            # Firefox Cookie 提取
```

## 已知限制

### Chrome 130+ App-Bound Encryption (ABE)

Chrome 130 及以上版本引入了 App-Bound Encryption（应用绑定加密）保护敏感 Cookie。
目前 `cookie_sync_native` 不支持解密 ABE 保护的 Cookie。

**影响范围:**
- Chrome 130+ 上访问 Google、Microsoft 等站点的敏感 Cookie 可能无法解密
- 其他站点和非敏感 Cookie 不受影响

**解决方案:**
1. 使用 Chrome 129 或更早版本
2. 使用完整的 HackBrowserData 工具（调用外部二进制文件）

如需了解详情，请参考：https://github.com/xaitax/Chrome-App-Bound-Encryption-Decryption

---

## 故障排除

### 1. 缺少依赖

```bash
pip install cryptography
```

### 2. macOS 上提示输入密码

这是正常的。首次访问 Keychain 时需要用户授权。

### 3. Windows 上权限错误

以管理员身份运行 PowerShell/CMD。

### 4. 浏览器运行时无法提取

关闭浏览器后再提取。浏览器运行时会锁定数据库文件。

### 5. Firefox 找不到配置文件

确保 Firefox 至少运行过一次（创建配置文件）。

## 与调用外部二进制方案的对比

| 特性 | 原生 Python | 调用 HackBrowserData |
|------|-------------|---------------------|
| 依赖 | Python + cryptography | 需要下载二进制文件 |
| 安装 | 简单 (pip install) | 需要下载、解压、配置路径 |
| 速度 | 快 | 更快 (Go 编译) |
| 功能 | Cookie 提取 | 密码、历史、书签等更多数据 |
| 维护 | 纯 Python，易调试 | 依赖外部项目更新 |

**建议:**
- 只需要 Cookie 同步 → 使用本原生 Python 版本
- 需要提取密码等其他数据 → 使用完整的 HackBrowserData

## License

MIT - 与 Web-Rooter 项目相同

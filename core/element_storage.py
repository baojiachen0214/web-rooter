"""
元素特征存储系统 - 用于自适应解析器

功能：
- 存储元素特征（标签名、属性、文本内容、相对位置等）
- 基于相似度计算找到最匹配的元素
- 支持缓存过期和清理
"""
import sqlite3
import json
import hashlib
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class ElementFeature:
    """元素特征数据"""
    url: str
    selector: str  # 原始选择器
    tag_name: str
    attributes: Dict[str, str] = field(default_factory=dict)
    text_content: str = ""
    text_hash: str = ""  # 文本哈希用于快速比较
    parent_path: str = ""  # 父元素路径
    sibling_index: int = 0  # 在兄弟元素中的位置
    child_count: int = 0  # 子元素数量
    class_list: List[str] = field(default_factory=list)
    id: Optional[str] = None
    name: Optional[str] = None
    xpath: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    last_accessed: datetime = field(default_factory=datetime.now)
    success_count: int = 0  # 成功定位次数
    failure_count: int = 0  # 失败次数

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "selector": self.selector,
            "tag_name": self.tag_name,
            "attributes": json.dumps(self.attributes),
            "text_content": self.text_content[:500],  # 限制长度
            "text_hash": self.text_hash,
            "parent_path": self.parent_path,
            "sibling_index": self.sibling_index,
            "child_count": self.child_count,
            "class_list": json.dumps(self.class_list),
            "id": self.id,
            "name": self.name,
            "xpath": self.xpath,
            "created_at": self.created_at.isoformat(),
            "access_count": self.access_count,
            "last_accessed": self.last_accessed.isoformat(),
            "success_count": self.success_count,
            "failure_count": self.failure_count,
        }

    @classmethod
    def from_row(cls, row: tuple) -> "ElementFeature":
        return cls(
            url=row[1],
            selector=row[2],
            tag_name=row[3],
            attributes=json.loads(row[4]) if row[4] else {},
            text_content=row[5] or "",
            text_hash=row[6] or "",
            parent_path=row[7] or "",
            sibling_index=row[8],
            child_count=row[9],
            class_list=json.loads(row[10]) if row[10] else [],
            id=row[11],
            name=row[12],
            xpath=row[13] or "",
            created_at=datetime.fromisoformat(row[14]),
            access_count=row[15],
            last_accessed=datetime.fromisoformat(row[16]),
            success_count=row[17],
            failure_count=row[18],
        )


class ElementStorageSystem:
    """元素特征存储系统"""

    def __init__(self, db_path: str = "./data/element_cache.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        """获取数据库连接"""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self):
        """初始化数据库"""
        conn = self._connect()
        cursor = conn.cursor()

        # 创建元素特征表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS element_features (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                selector TEXT NOT NULL,
                tag_name TEXT NOT NULL,
                attributes TEXT,
                text_content TEXT,
                text_hash TEXT,
                parent_path TEXT,
                sibling_index INTEGER,
                child_count INTEGER,
                class_list TEXT,
                element_id TEXT,
                name_attr TEXT,
                xpath TEXT,
                created_at TEXT,
                access_count INTEGER DEFAULT 0,
                last_accessed TEXT,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                UNIQUE(url, selector)
            )
        """)

        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_url ON element_features(url)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_selector ON element_features(selector)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tag_name ON element_features(tag_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON element_features(created_at)")

        conn.commit()
        logger.info(f"Element storage initialized at {self.db_path}")

    def save_feature(self, feature: ElementFeature) -> bool:
        """保存元素特征"""
        conn = self._connect()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT OR REPLACE INTO element_features
                (url, selector, tag_name, attributes, text_content, text_hash,
                 parent_path, sibling_index, child_count, class_list, element_id, name_attr, xpath,
                 created_at, access_count, last_accessed, success_count, failure_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                feature.url,
                feature.selector,
                feature.tag_name,
                json.dumps(feature.attributes),
                feature.text_content[:1000],
                feature.text_hash,
                feature.parent_path,
                feature.sibling_index,
                feature.child_count,
                json.dumps(feature.class_list),
                feature.id,
                feature.name,
                feature.xpath,
                feature.created_at.isoformat(),
                feature.access_count,
                feature.last_accessed.isoformat(),
                feature.success_count,
                feature.failure_count,
            ))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error saving element feature: {e}")
            conn.rollback()
            return False

    def get_features(self, url: str, selector: str) -> List[ElementFeature]:
        """获取元素的特征列表"""
        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM element_features
            WHERE url = ? OR selector = ?
            ORDER BY success_count DESC, access_count DESC, created_at DESC
        """, (url, selector))

        return [ElementFeature.from_row(row) for row in cursor.fetchall()]

    def update_access(self, feature: ElementFeature, success: bool):
        """更新访问统计"""
        conn = self._connect()
        cursor = conn.cursor()

        feature.access_count += 1
        feature.last_accessed = datetime.now()
        if success:
            feature.success_count += 1
        else:
            feature.failure_count += 1

        cursor.execute("""
            UPDATE element_features
            SET access_count = ?, last_accessed = ?, success_count = ?, failure_count = ?
            WHERE url = ? AND selector = ?
        """, (
            feature.access_count,
            feature.last_accessed.isoformat(),
            feature.success_count,
            feature.failure_count,
            feature.url,
            feature.selector,
        ))
        conn.commit()

    def cleanup_expired(self, days: int = 30) -> int:
        """清理过期缓存"""
        conn = self._connect()
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        cursor.execute("""
            DELETE FROM element_features
            WHERE last_accessed < ?
        """, (cutoff_date,))

        deleted = cursor.rowcount
        conn.commit()
        logger.info(f"Cleaned up {deleted} expired element features")
        return deleted

    def cleanup_low_success(self, min_success_rate: float = 0.3) -> int:
        """清理低成功率的缓存"""
        conn = self._connect()
        cursor = conn.cursor()

        # 删除成功率低于阈值的记录（至少有过 3 次尝试）
        cursor.execute("""
            DELETE FROM element_features
            WHERE success_count + failure_count >= 3
            AND CAST(success_count AS FLOAT) / (success_count + failure_count) < ?
        """, (min_success_rate,))

        deleted = cursor.rowcount
        conn.commit()
        logger.info(f"Cleaned up {deleted} low-success element features")
        return deleted

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        conn = self._connect()
        cursor = conn.cursor()

        stats = {}

        # 总元素数
        cursor.execute("SELECT COUNT(*) FROM element_features")
        stats["total_elements"] = cursor.fetchone()[0]

        # 按标签统计
        cursor.execute("""
            SELECT tag_name, COUNT(*) as count
            FROM element_features
            GROUP BY tag_name
            ORDER BY count DESC
        """)
        stats["by_tag"] = {row[0]: row[1] for row in cursor.fetchall()}

        # 平均成功率
        cursor.execute("""
            SELECT AVG(CAST(success_count AS FLOAT) / (success_count + failure_count + 0.001))
            FROM element_features
        """)
        stats["avg_success_rate"] = cursor.fetchone()[0] or 0

        # 数据库大小
        stats["db_size_bytes"] = self.db_path.stat().st_size if self.db_path.exists() else 0

        return stats

    def close(self):
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "ElementStorageSystem":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def compute_text_hash(text: str) -> str:
    """计算文本哈希"""
    # 规范化文本：去除空白、转小写
    normalized = " ".join(text.lower().split())
    return hashlib.md5(normalized.encode()).hexdigest()[:16]


def get_parent_path(element, max_depth: int = 5) -> str:
    """获取元素的父元素路径"""
    path = []
    current = element.parent
    depth = 0

    while current and depth < max_depth:
        if hasattr(current, "name") and current.name:
            path.append(current.name)
        current = current.parent
        depth += 1

    return " > ".join(reversed(path))


def get_sibling_index(element) -> int:
    """获取元素在兄弟元素中的位置"""
    parent = element.parent
    if not parent:
        return 0

    siblings = [s for s in parent.children if hasattr(s, "name") and s.name == element.name]
    for i, sibling in enumerate(siblings):
        if sibling is element:
            return i
    return 0


def generate_xpath(element) -> str:
    """生成元素的 XPath"""
    path = []
    current = element

    while current and hasattr(current, "name") and current.name:
        parent = current.parent
        if parent:
            siblings = [s for s in parent.children
                       if hasattr(s, "name") and s.name == current.name]
            if len(siblings) > 1:
                index = siblings.index(current) + 1
                path.append(f"{current.name}[{index}]")
            else:
                path.append(current.name)
        else:
            path.append(current.name)
        current = parent

    return "/" + "/".join(reversed(path))


def element_to_feature(element, selector: str = "", url: str = "") -> ElementFeature:
    """
    从 BeautifulSoup 元素创建 ElementFeature

    Args:
        element: BeautifulSoup Tag 元素
        selector: CSS 选择器
        url: 页面 URL

    Returns:
        ElementFeature 对象
    """
    from bs4 import Tag

    if not isinstance(element, Tag):
        raise ValueError("Element must be a BeautifulSoup Tag")

    text = element.get_text(strip=True)[:200]

    return ElementFeature(
        url=url,
        selector=selector,
        tag_name=element.name or "",
        attributes={k: str(v) for k, v in element.attrs.items() if k not in ["class", "id"]},
        text_content=text,
        text_hash=compute_text_hash(text),
        parent_path=get_parent_path(element),
        sibling_index=get_sibling_index(element),
        child_count=len(list(element.children)),
        class_list=element.get("class", []),
        id=element.get("id"),
        name=element.get("name"),
        xpath=generate_xpath(element),
    )


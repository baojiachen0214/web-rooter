"""Social-platform specific readers and helpers."""

from .bilibili_reader import (
    extract_bilibili_video_ref,
    is_bilibili_detail_url,
    is_bilibili_video_url,
    read_bilibili_detail,
)
from .xiaohongshu_reader import (
    extract_xiaohongshu_note_ref,
    is_xiaohongshu_detail_url,
    read_xiaohongshu_note,
)

__all__ = [
    "extract_bilibili_video_ref",
    "extract_xiaohongshu_note_ref",
    "is_bilibili_detail_url",
    "is_bilibili_video_url",
    "is_xiaohongshu_detail_url",
    "read_bilibili_detail",
    "read_xiaohongshu_note",
]

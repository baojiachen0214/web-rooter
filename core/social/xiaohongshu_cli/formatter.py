"""
Output formatting for XHS CLI - Rich-based formatting for Web-Rooter.
"""

from __future__ import annotations

import json
from typing import Any

from .constants import HOME_URL


def format_note_summary(note: dict[str, Any]) -> str:
    """Format a note for list display."""
    title = note.get("title", "Untitled")
    note_id = note.get("note_id", note.get("id", "unknown"))
    author = note.get("user", {}).get("nickname", "Unknown")
    likes = note.get("interact_info", {}).get("liked_count", note.get("liked_count", 0))
    
    return f"[{note_id[:8]}...] {title[:40]} by @{author} (❤️ {likes})"


def format_note_detail(note: dict[str, Any]) -> str:
    """Format full note details."""
    lines = []
    
    title = note.get("title", "Untitled")
    lines.append(f"📌 {title}")
    lines.append("-" * 60)
    
    note_id = note.get("note_id", note.get("id", "unknown"))
    lines.append(f"ID: {note_id}")
    
    user = note.get("user", {})
    lines.append(f"Author: @{user.get('nickname', 'Unknown')} ({user.get('user_id', 'N/A')})")
    
    interact = note.get("interact_info", {})
    lines.append(f"Likes: {interact.get('liked_count', 0)} | "
                f"Comments: {interact.get('comment_count', 0)} | "
                f"Favorites: {interact.get('collected_count', 0)}")
    
    lines.append(f"URL: {HOME_URL}/explore/{note_id}")
    lines.append("-" * 60)
    
    desc = note.get("desc", note.get("content", ""))
    if desc:
        lines.append("Content:")
        lines.append(desc[:500] + "..." if len(desc) > 500 else desc)
    
    return "\n".join(lines)


def format_comment(comment: dict[str, Any], index: int = 0) -> str:
    """Format a comment for display."""
    user_info = comment.get("user_info", comment.get("user", {}))
    nickname = user_info.get("nickname", "Anonymous")
    content = comment.get("content_info", {}).get("content", comment.get("content", ""))
    likes = comment.get("like_count", 0)
    
    prefix = f"{index}. " if index else "• "
    return f"{prefix}@{nickname}: {content[:100]} (❤️ {likes})"


def format_comments(comments: list[dict], title: str = "Comments") -> str:
    """Format a list of comments."""
    lines = [f"\n💬 {title} ({len(comments)} total)", "=" * 60]
    
    for i, comment in enumerate(comments[:20], 1):
        lines.append(format_comment(comment, i))
    
    if len(comments) > 20:
        lines.append(f"\n... and {len(comments) - 20} more")
    
    return "\n".join(lines)


def format_user_info(user: dict[str, Any]) -> str:
    """Format user profile info."""
    lines = []
    lines.append(f"👤 {user.get('nickname', 'Unknown')}")
    lines.append(f"ID: {user.get('user_id', user.get('id', 'N/A'))}")
    lines.append(f"Followers: {user.get('fans', user.get('follower_count', 0))}")
    lines.append(f"Following: {user.get('follows', user.get('follow_count', 0))}")
    lines.append(f"Notes: {user.get('note_count', 0)}")
    
    desc = user.get("desc", user.get("signature", ""))
    if desc:
        lines.append(f"\nBio: {desc}")
    
    return "\n".join(lines)


def format_search_results(data: dict[str, Any]) -> str:
    """Format search results."""
    items = data.get("items", [])
    lines = [f"🔍 Search Results ({len(items)} items)", "=" * 60]
    
    for i, item in enumerate(items[:10], 1):
        note = item.get("note_card", item)
        lines.append(f"{i}. {format_note_summary(note)}")
    
    if len(items) > 10:
        lines.append(f"\n... and {len(items) - 10} more")
    
    return "\n".join(lines)


def format_json(data: Any) -> str:
    """Format data as JSON string."""
    return json.dumps(data, ensure_ascii=False, indent=2)


def print_success(message: str) -> None:
    """Print success message."""
    print(f"✅ {message}")


def print_error(message: str) -> None:
    """Print error message."""
    print(f"❌ {message}")


def print_info(message: str) -> None:
    """Print info message."""
    print(f"ℹ️  {message}")


def format_notification(notification: dict[str, Any]) -> str:
    """Format a notification for display."""
    notif_type = notification.get("type", "unknown")
    user_info = notification.get("user_info", notification.get("user", {}))
    nickname = user_info.get("nickname", "Someone")
    
    if notif_type == "like":
        target = notification.get("target", {})
        target_title = target.get("title", "your note")
        return f"❤️  @{nickname} liked {target_title[:30]}"
    
    elif notif_type == "comment" or notif_type == "mention":
        content = notification.get("content", notification.get("comment_content", ""))
        return f"💬 @{nickname} mentioned you: {content[:50]}"
    
    elif notif_type == "follow":
        return f"👥 @{nickname} started following you"
    
    else:
        title = notification.get("title", "")
        content = notification.get("content", "")
        if title and content:
            return f"📢 {title}: {content[:50]}"
        return f"📢 {title or content or str(notification)[:50]}"

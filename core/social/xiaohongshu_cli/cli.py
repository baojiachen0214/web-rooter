"""
CLI entry point for `wr xhs` command - Web-Rooter integrated XHS CLI.

Usage:
    wr xhs search <keyword>
    wr xhs read <note_id_or_url>
    wr xhs comments <note_id_or_url>
    wr xhs user <user_id>
    ... and more
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

from .client import XhsClient
from .cookies import get_cookies, save_cookies, clear_cookies
from .exceptions import XhsApiError, NoCookieError
from .formatter import (
    format_note_detail,
    format_comments,
    format_user_info,
    format_search_results,
    format_json,
    print_success,
    print_error,
    print_info,
    format_notification,
)
from .note_refs import resolve_note_reference, save_index_from_items, save_index_from_notes

logger = logging.getLogger(__name__)


def get_client() -> XhsClient:
    """Get XHS client with cookies from auth_profiles or saved."""
    try:
        source, cookies = get_cookies()
        logger.debug("Using cookies from: %s", source)
        return XhsClient(cookies)
    except NoCookieError as e:
        print_error(str(e))
        sys.exit(1)


def cmd_search(args: argparse.Namespace) -> int:
    """Search notes."""
    client = get_client()
    
    sort_map = {"general": "general", "popular": "popularity_descending", "latest": "time_descending"}
    type_map = {"all": 0, "video": 1, "image": 2}
    
    try:
        result = client.search_notes(
            keyword=args.keyword,
            page=args.page,
            sort=sort_map.get(args.sort, "general"),
            note_type=type_map.get(args.type, 0),
        )
        
        save_index_from_items(result, xsec_source="pc_search")
        
        if args.json:
            print(format_json(result))
        else:
            print(format_search_results(result))
        
        return 0
    except XhsApiError as e:
        print_error(f"Search failed: {e}")
        return 1


def cmd_read(args: argparse.Namespace) -> int:
    """Read a note by ID or URL."""
    client = get_client()
    
    try:
        note_id, token, source = resolve_note_reference(args.id_or_url, xsec_token=args.xsec_token or "")
        
        result = client.get_note_detail(note_id, xsec_token=token, xsec_source=source)
        
        if args.json:
            print(format_json(result))
        else:
            print(format_note_detail(result))
        
        return 0
    except XhsApiError as e:
        print_error(f"Failed to read note: {e}")
        return 1


def cmd_comments(args: argparse.Namespace) -> int:
    """Get comments for a note."""
    client = get_client()
    
    try:
        note_id, token, source = resolve_note_reference(args.id_or_url, xsec_token=args.xsec_token or "")
        
        if args.all:
            result = client.get_all_comments(note_id, xsec_token=token, xsec_source=source)
            comments = result.get("comments", [])
            print_info(f"Fetched {result.get('total_fetched', 0)} comments across {result.get('pages_fetched', 0)} pages")
        else:
            result = client.get_comments(note_id, cursor=args.cursor, xsec_token=token, xsec_source=source)
            comments = result.get("comments", [])
        
        if args.json:
            print(format_json(result))
        else:
            print(format_comments(comments))
        
        return 0
    except XhsApiError as e:
        print_error(f"Failed to get comments: {e}")
        return 1


def cmd_user(args: argparse.Namespace) -> int:
    """Get user info."""
    client = get_client()
    
    try:
        result = client.get_user_info(args.user_id)
        
        if args.json:
            print(format_json(result))
        else:
            print(format_user_info(result))
        
        return 0
    except XhsApiError as e:
        print_error(f"Failed to get user info: {e}")
        return 1


def cmd_user_posts(args: argparse.Namespace) -> int:
    """Get user's posts."""
    client = get_client()
    
    try:
        result = client.get_user_notes(args.user_id, cursor=args.cursor)
        
        notes = result.get("notes", [])
        save_index_from_notes(notes)
        
        if args.json:
            print(format_json(result))
        else:
            for i, note in enumerate(notes[:10], 1):
                print(f"{i}. {note.get('title', 'Untitled')}")
            
            if result.get("has_more"):
                print_info(f"More notes available — use --cursor {result.get('cursor', '')}")
        
        return 0
    except XhsApiError as e:
        print_error(f"Failed to get user posts: {e}")
        return 1


def cmd_feed(args: argparse.Namespace) -> int:
    """Get home feed."""
    client = get_client()
    
    try:
        result = client.get_home_feed()
        
        save_index_from_items(result, xsec_source="pc_feed")
        
        if args.json:
            print(format_json(result))
        else:
            items = result.get("items", [])
            for i, item in enumerate(items[:10], 1):
                note = item.get("note_card", item)
                print(f"{i}. {note.get('title', 'Untitled')}")
        
        return 0
    except XhsApiError as e:
        print_error(f"Failed to get feed: {e}")
        return 1


def cmd_like(args: argparse.Namespace) -> int:
    """Like a note."""
    client = get_client()
    
    try:
        note_id = resolve_note_reference(args.note_id)[0]
        client.like_note(note_id)
        print_success(f"Liked note {note_id}")
        return 0
    except XhsApiError as e:
        print_error(f"Failed to like note: {e}")
        return 1


def cmd_unlike(args: argparse.Namespace) -> int:
    """Unlike a note."""
    client = get_client()
    
    try:
        note_id = resolve_note_reference(args.note_id)[0]
        client.unlike_note(note_id)
        print_success(f"Unliked note {note_id}")
        return 0
    except XhsApiError as e:
        print_error(f"Failed to unlike note: {e}")
        return 1


def cmd_favorite(args: argparse.Namespace) -> int:
    """Favorite a note."""
    client = get_client()
    
    try:
        note_id = resolve_note_reference(args.note_id)[0]
        client.favorite_note(note_id)
        print_success(f"Favorited note {note_id}")
        return 0
    except XhsApiError as e:
        print_error(f"Failed to favorite note: {e}")
        return 1


def cmd_unfavorite(args: argparse.Namespace) -> int:
    """Unfavorite a note."""
    client = get_client()
    
    try:
        note_id = resolve_note_reference(args.note_id)[0]
        client.unfavorite_note(note_id)
        print_success(f"Unfavorited note {note_id}")
        return 0
    except XhsApiError as e:
        print_error(f"Failed to unfavorite note: {e}")
        return 1


def cmd_follow(args: argparse.Namespace) -> int:
    """Follow a user."""
    client = get_client()
    
    try:
        client.follow_user(args.user_id)
        print_success(f"Followed user {args.user_id}")
        return 0
    except XhsApiError as e:
        print_error(f"Failed to follow user: {e}")
        return 1


def cmd_unfollow(args: argparse.Namespace) -> int:
    """Unfollow a user."""
    client = get_client()
    
    try:
        client.unfollow_user(args.user_id)
        print_success(f"Unfollowed user {args.user_id}")
        return 0
    except XhsApiError as e:
        print_error(f"Failed to unfollow user: {e}")
        return 1


def cmd_favorites(args: argparse.Namespace) -> int:
    """Get user's favorites."""
    client = get_client()
    
    try:
        user_id = args.user_id or client.get_self_info().get("user_id", "")
        result = client.get_user_favorites(user_id, cursor=args.cursor)
        
        if args.json:
            print(format_json(result))
        else:
            for note in result.get("notes", [])[:10]:
                print(f"• {note.get('title', 'Untitled')}")
        
        return 0
    except XhsApiError as e:
        print_error(f"Failed to get favorites: {e}")
        return 1


def cmd_comment(args: argparse.Namespace) -> int:
    """Post a comment."""
    client = get_client()
    
    try:
        note_id = resolve_note_reference(args.note_id)[0]
        client.post_comment(note_id, args.content)
        print_success("Comment posted")
        return 0
    except XhsApiError as e:
        print_error(f"Failed to post comment: {e}")
        return 1


def cmd_my_notes(args: argparse.Namespace) -> int:
    """Get my notes."""
    client = get_client()
    
    try:
        result = client.get_creator_note_list(page=args.page)
        
        notes = result.get("notes", result.get("note_list", []))
        save_index_from_notes(notes)
        
        if args.json:
            print(format_json(result))
        else:
            for i, note in enumerate(notes[:10], 1):
                print(f"{i}. {note.get('title', 'Untitled')}")
        
        return 0
    except XhsApiError as e:
        print_error(f"Failed to get my notes: {e}")
        return 1


def cmd_whoami(args: argparse.Namespace) -> int:
    """Get current user info."""
    client = get_client()
    
    try:
        result = client.get_self_info()
        
        if args.json:
            print(format_json(result))
        else:
            print(format_user_info(result))
        
        return 0
    except XhsApiError as e:
        print_error(f"Failed to get user info: {e}")
        return 1


def cmd_logout(args: argparse.Namespace) -> int:
    """Clear saved cookies."""
    clear_cookies()
    print_success("Logged out — cookies cleared")
    return 0


def cmd_login(args: argparse.Namespace) -> int:
    """Login via QR code."""
    from .qr_login import qrcode_login, BrowserQrLoginUnavailable
    
    def on_status(msg: str) -> None:
        print(msg)
    
    try:
        cookies = qrcode_login(
            on_status=on_status,
            timeout_s=args.timeout,
            prefer_browser_assisted=args.browser
        )
        print_success(f"\n✅ Login successful! Saved {len(cookies)} cookies.")
        print_info("You can now use 'wr xhs' commands.")
        return 0
    except BrowserQrLoginUnavailable as e:
        print_error(f"Browser login unavailable: {e}")
        print_info("Falling back to HTTP QR login...")
        try:
            cookies = qrcode_login(on_status=on_status, timeout_s=args.timeout, prefer_browser_assisted=False)
            print_success(f"\n✅ Login successful! Saved {len(cookies)} cookies.")
            return 0
        except Exception as e2:
            print_error(f"Login failed: {e2}")
            return 1
    except Exception as e:
        print_error(f"Login failed: {e}")
        return 1


def cmd_status(args: argparse.Namespace) -> int:
    """Check login status."""
    try:
        source, cookies = get_cookies()
        client = XhsClient(cookies)
        
        try:
            self_info = client.get_self_info()
            user_id = self_info.get("user_id", "unknown")
            nickname = self_info.get("nickname", "unknown")
            
            print_success(f"✅ Logged in as {nickname} (ID: {user_id})")
            print_info(f"Cookie source: {source}")
            
            if args.json:
                print(format_json({"status": "logged_in", "user": self_info}))
            
            return 0
        except XhsApiError as e:
            if "login" in str(e).lower() or "session" in str(e).lower():
                print_error("❌ Session expired or invalid")
                print_info("Please login again: wr xhs login")
                return 1
            raise
    except NoCookieError:
        print_error("❌ Not logged in")
        print_info("Please login: wr xhs login")
        return 1
    except Exception as e:
        print_error(f"Failed to check status: {e}")
        return 1


def cmd_hot(args: argparse.Namespace) -> int:
    """Get hot/trending feed."""
    client = get_client()
    
    try:
        result = client.get_hot_feed(category=args.category)
        
        save_index_from_items(result, xsec_source="pc_hot")
        
        if args.json:
            print(format_json(result))
        else:
            items = result.get("items", [])
            print_info(f"Hot feed ({len(items)} items):\n")
            for i, item in enumerate(items[:20], 1):
                note = item.get("note_card", item)
                title = note.get("title", "Untitled")
                author = note.get("user", {}).get("nickname", "Unknown")
                likes = note.get("likes", note.get("like_count", 0))
                print(f"{i}. {title}")
                print(f"   👤 {author} | ❤️ {likes}")
                print()
        
        return 0
    except XhsApiError as e:
        print_error(f"Failed to get hot feed: {e}")
        return 1


def cmd_topics(args: argparse.Namespace) -> int:
    """Search topics."""
    client = get_client()
    
    try:
        result = client.search_topics(args.keyword)
        
        if args.json:
            print(format_json(result))
        else:
            topics = result.get("topics", [])
            print_info(f"Found {len(topics)} topics for '{args.keyword}':\n")
            for i, topic in enumerate(topics[:20], 1):
                name = topic.get("name", "Unknown")
                view_count = topic.get("view_count", topic.get("view_num", 0))
                discuss_count = topic.get("discuss_count", topic.get("discuss_num", 0))
                print(f"{i}. #{name}")
                print(f"   👁 {view_count} views | 💬 {discuss_count} discussions")
                print()
        
        return 0
    except XhsApiError as e:
        print_error(f"Failed to search topics: {e}")
        return 1


def cmd_search_user(args: argparse.Namespace) -> int:
    """Search users."""
    client = get_client()
    
    try:
        result = client.search_users(args.keyword)
        
        if args.json:
            print(format_json(result))
        else:
            users = result.get("users", [])
            print_info(f"Found {len(users)} users for '{args.keyword}':\n")
            for i, user in enumerate(users[:20], 1):
                user_id = user.get("id", user.get("user_id", "Unknown"))
                nickname = user.get("nickname", "Unknown")
                followers = user.get("followers", user.get("follows", "Unknown"))
                desc = user.get("desc", "")
                print(f"{i}. {nickname} (ID: {user_id})")
                print(f"   👥 Followers: {followers}")
                if desc:
                    print(f"   📝 {desc[:60]}...")
                print()
        
        return 0
    except XhsApiError as e:
        print_error(f"Failed to search users: {e}")
        return 1


def cmd_sub_comments(args: argparse.Namespace) -> int:
    """Get sub-comments (replies) for a comment."""
    client = get_client()
    
    try:
        note_id, token, source = resolve_note_reference(args.note_id, xsec_token=args.xsec_token or "")
        
        result = client.get_sub_comments(
            note_id=note_id,
            comment_id=args.comment_id,
            num=args.num,
            cursor=args.cursor,
            xsec_token=token,
            xsec_source=source
        )
        
        if args.json:
            print(format_json(result))
        else:
            comments = result.get("comments", [])
            print_info(f"Sub-comments ({len(comments)}):\n")
            print(format_comments(comments))
        
        return 0
    except XhsApiError as e:
        print_error(f"Failed to get sub-comments: {e}")
        return 1


def cmd_reply(args: argparse.Namespace) -> int:
    """Reply to a comment."""
    client = get_client()
    
    try:
        note_id = resolve_note_reference(args.note_id)[0]
        client.reply_comment(note_id, args.comment_id, args.content)
        print_success("Reply posted")
        return 0
    except XhsApiError as e:
        print_error(f"Failed to post reply: {e}")
        return 1


def cmd_delete_comment(args: argparse.Namespace) -> int:
    """Delete a comment."""
    client = get_client()
    
    try:
        note_id = resolve_note_reference(args.note_id)[0]
        client.delete_comment(note_id, args.comment_id)
        print_success("Comment deleted")
        return 0
    except XhsApiError as e:
        print_error(f"Failed to delete comment: {e}")
        return 1


def cmd_likes(args: argparse.Namespace) -> int:
    """Get user's liked notes."""
    client = get_client()
    
    try:
        user_id = args.user_id or client.get_self_info().get("user_id", "")
        result = client.get_user_likes(user_id, cursor=args.cursor)
        
        if args.json:
            print(format_json(result))
        else:
            notes = result.get("notes", [])
            print_info(f"Liked notes ({len(notes)}):\n")
            for note in notes[:10]:
                print(f"• {note.get('title', 'Untitled')}")
        
        return 0
    except XhsApiError as e:
        print_error(f"Failed to get likes: {e}")
        return 1


def cmd_post(args: argparse.Namespace) -> int:
    """Post a new note (image type only for now)."""
    client = get_client()
    
    try:
        # Get upload permit and upload images
        image_files = args.images.split(",") if args.images else []
        if not image_files:
            print_error("At least one image is required")
            return 1
        
        print_info(f"Uploading {len(image_files)} images...")
        
        # Upload each image
        file_ids = []
        for img_path in image_files:
            img_path = img_path.strip()
            permit = client.get_upload_permit("image", 1)
            uploaded = client.upload_file(img_path, permit)
            file_ids.append(uploaded["file_id"])
        
        # Create the note
        result = client.create_image_note(
            title=args.title,
            desc=args.desc or args.title,
            file_ids=file_ids
        )
        
        print_success(f"Note posted! ID: {result.get('note_id', 'unknown')}")
        return 0
    except XhsApiError as e:
        print_error(f"Failed to post note: {e}")
        return 1


def cmd_delete(args: argparse.Namespace) -> int:
    """Delete a note."""
    client = get_client()
    
    try:
        note_id = resolve_note_reference(args.note_id)[0]
        
        if not args.yes:
            confirm = input(f"Delete note {note_id}? [y/N]: ")
            if confirm.lower() != "y":
                print_info("Cancelled")
                return 0
        
        client.delete_note(note_id)
        print_success(f"Note {note_id} deleted")
        return 0
    except XhsApiError as e:
        print_error(f"Failed to delete note: {e}")
        return 1


def cmd_notifications(args: argparse.Namespace) -> int:
    """Get notifications."""
    client = get_client()
    
    try:
        if args.type == "mentions":
            result = client.get_notification_mentions(cursor=args.cursor, num=args.num)
        elif args.type == "likes":
            result = client.get_notification_likes(cursor=args.cursor, num=args.num)
        elif args.type == "connections":
            result = client.get_notification_connections(cursor=args.cursor, num=args.num)
        else:
            # Default to mentions
            result = client.get_notification_mentions(cursor=args.cursor, num=args.num)
        
        if args.json:
            print(format_json(result))
        else:
            notifications = result.get("notifications", result.get("message_list", []))
            print_info(f"Notifications ({len(notifications)}):\n")
            for notif in notifications[:20]:
                print(format_notification(notif))
        
        return 0
    except XhsApiError as e:
        print_error(f"Failed to get notifications: {e}")
        return 1


def cmd_unread(args: argparse.Namespace) -> int:
    """Get unread notification count."""
    client = get_client()
    
    try:
        result = client.get_unread_count()
        
        if args.json:
            print(format_json(result))
        else:
            mentions = result.get("mention_count", 0)
            likes = result.get("like_count", 0)
            connections = result.get("follow_count", result.get("connection_count", 0))
            total = result.get("total_count", mentions + likes + connections)
            
            print_info("Unread notifications:")
            print(f"  💬 Mentions: {mentions}")
            print(f"  ❤️  Likes: {likes}")
            print(f"  👥 Connections: {connections}")
            print(f"  📊 Total: {total}")
        
        return 0
    except XhsApiError as e:
        print_error(f"Failed to get unread count: {e}")
        return 1


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser for wr xhs command."""
    parser = argparse.ArgumentParser(
        prog="wr xhs",
        description="""Xiaohongshu CLI - Integrated with Web-Rooter

⚠️  IMPORTANT RISK DISCLAIMER:
    This tool directly calls XHS internal APIs based on jackwener/xiaohongshu-cli.
    - Risk of ACCOUNT BAN/SUSPENSION exists for frequent API usage
    - Login required via QR code or browser cookie sync
    - Use a TEST ACCOUNT only, not your main account
    - Control operation frequency, avoid batch operations
    - For search/browse only, prefer 'wr social --platform=xiaohongshu' (safer)

    By using this tool, you accept all risks associated with XHS account suspension.
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Global options
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    # search
    search_parser = subparsers.add_parser("search", help="Search notes")
    search_parser.add_argument("keyword", help="Search keyword")
    search_parser.add_argument("--sort", choices=["general", "popular", "latest"], default="general")
    search_parser.add_argument("--type", choices=["all", "video", "image"], default="all")
    search_parser.add_argument("--page", type=int, default=1)
    search_parser.set_defaults(func=cmd_search)
    
    # read
    read_parser = subparsers.add_parser("read", help="Read a note")
    read_parser.add_argument("id_or_url", help="Note ID or URL")
    read_parser.add_argument("--xsec-token", help="Security token")
    read_parser.set_defaults(func=cmd_read)
    
    # comments
    comments_parser = subparsers.add_parser("comments", help="Get comments")
    comments_parser.add_argument("id_or_url", help="Note ID or URL")
    comments_parser.add_argument("--xsec-token", help="Security token")
    comments_parser.add_argument("--cursor", default="", help="Pagination cursor")
    comments_parser.add_argument("--all", action="store_true", help="Get all comments")
    comments_parser.set_defaults(func=cmd_comments)
    
    # user
    user_parser = subparsers.add_parser("user", help="Get user info")
    user_parser.add_argument("user_id", help="User ID")
    user_parser.set_defaults(func=cmd_user)
    
    # user-posts
    user_posts_parser = subparsers.add_parser("user-posts", help="Get user's posts")
    user_posts_parser.add_argument("user_id", help="User ID")
    user_posts_parser.add_argument("--cursor", default="", help="Pagination cursor")
    user_posts_parser.set_defaults(func=cmd_user_posts)
    
    # feed
    feed_parser = subparsers.add_parser("feed", help="Get home feed")
    feed_parser.set_defaults(func=cmd_feed)
    
    # like/unlike
    like_parser = subparsers.add_parser("like", help="Like a note")
    like_parser.add_argument("note_id", help="Note ID or URL")
    like_parser.set_defaults(func=cmd_like)
    
    unlike_parser = subparsers.add_parser("unlike", help="Unlike a note")
    unlike_parser.add_argument("note_id", help="Note ID or URL")
    unlike_parser.set_defaults(func=cmd_unlike)
    
    # favorite/unfavorite
    favorite_parser = subparsers.add_parser("favorite", help="Favorite a note")
    favorite_parser.add_argument("note_id", help="Note ID or URL")
    favorite_parser.set_defaults(func=cmd_favorite)
    
    unfavorite_parser = subparsers.add_parser("unfavorite", help="Unfavorite a note")
    unfavorite_parser.add_argument("note_id", help="Note ID or URL")
    unfavorite_parser.set_defaults(func=cmd_unfavorite)
    
    # follow/unfollow
    follow_parser = subparsers.add_parser("follow", help="Follow a user")
    follow_parser.add_argument("user_id", help="User ID")
    follow_parser.set_defaults(func=cmd_follow)
    
    unfollow_parser = subparsers.add_parser("unfollow", help="Unfollow a user")
    unfollow_parser.add_argument("user_id", help="User ID")
    unfollow_parser.set_defaults(func=cmd_unfollow)
    
    # favorites
    favorites_parser = subparsers.add_parser("favorites", help="Get favorites")
    favorites_parser.add_argument("user_id", nargs="?", help="User ID (default: self)")
    favorites_parser.add_argument("--cursor", default="", help="Pagination cursor")
    favorites_parser.set_defaults(func=cmd_favorites)
    
    # comment
    comment_parser = subparsers.add_parser("comment", help="Post a comment")
    comment_parser.add_argument("note_id", help="Note ID or URL")
    comment_parser.add_argument("--content", required=True, help="Comment content")
    comment_parser.set_defaults(func=cmd_comment)
    
    # my-notes
    my_notes_parser = subparsers.add_parser("my-notes", help="Get my notes")
    my_notes_parser.add_argument("--page", type=int, default=0)
    my_notes_parser.set_defaults(func=cmd_my_notes)
    
    # whoami
    whoami_parser = subparsers.add_parser("whoami", help="Get current user info")
    whoami_parser.set_defaults(func=cmd_whoami)
    
    # logout
    logout_parser = subparsers.add_parser("logout", help="Logout and clear cookies")
    logout_parser.set_defaults(func=cmd_logout)
    
    # login (NEW)
    login_parser = subparsers.add_parser("login", help="Login via QR code")
    login_parser.add_argument("--browser", action="store_true", help="Use browser-assisted login")
    login_parser.add_argument("--timeout", type=int, default=240, help="QR code timeout in seconds")
    login_parser.set_defaults(func=cmd_login)
    
    # status (NEW)
    status_parser = subparsers.add_parser("status", help="Check login status")
    status_parser.set_defaults(func=cmd_status)
    
    # hot (NEW)
    hot_parser = subparsers.add_parser("hot", help="Get hot/trending feed")
    hot_parser.add_argument("--category", default="homefeed.fashion_v3", help="Hot category")
    hot_parser.set_defaults(func=cmd_hot)
    
    # topics (NEW)
    topics_parser = subparsers.add_parser("topics", help="Search topics")
    topics_parser.add_argument("keyword", help="Search keyword")
    topics_parser.set_defaults(func=cmd_topics)
    
    # search-user (NEW)
    search_user_parser = subparsers.add_parser("search-user", help="Search users")
    search_user_parser.add_argument("keyword", help="Search keyword")
    search_user_parser.set_defaults(func=cmd_search_user)
    
    # sub-comments (NEW)
    sub_comments_parser = subparsers.add_parser("sub-comments", help="Get sub-comments (replies)")
    sub_comments_parser.add_argument("note_id", help="Note ID or URL")
    sub_comments_parser.add_argument("comment_id", help="Parent comment ID")
    sub_comments_parser.add_argument("--num", type=int, default=10, help="Number of replies")
    sub_comments_parser.add_argument("--cursor", default="", help="Pagination cursor")
    sub_comments_parser.add_argument("--xsec-token", help="Security token")
    sub_comments_parser.set_defaults(func=cmd_sub_comments)
    
    # reply (NEW)
    reply_parser = subparsers.add_parser("reply", help="Reply to a comment")
    reply_parser.add_argument("note_id", help="Note ID or URL")
    reply_parser.add_argument("--comment-id", required=True, help="Comment ID to reply to")
    reply_parser.add_argument("--content", required=True, help="Reply content")
    reply_parser.set_defaults(func=cmd_reply)
    
    # delete-comment (NEW)
    delete_comment_parser = subparsers.add_parser("delete-comment", help="Delete a comment")
    delete_comment_parser.add_argument("note_id", help="Note ID or URL")
    delete_comment_parser.add_argument("--comment-id", required=True, help="Comment ID to delete")
    delete_comment_parser.set_defaults(func=cmd_delete_comment)
    
    # likes (NEW)
    likes_parser = subparsers.add_parser("likes", help="Get user's liked notes")
    likes_parser.add_argument("user_id", nargs="?", help="User ID (default: self)")
    likes_parser.add_argument("--cursor", default="", help="Pagination cursor")
    likes_parser.set_defaults(func=cmd_likes)
    
    # post (NEW)
    post_parser = subparsers.add_parser("post", help="Post a new note")
    post_parser.add_argument("--title", required=True, help="Note title")
    post_parser.add_argument("--desc", help="Note description")
    post_parser.add_argument("--images", required=True, help="Comma-separated image paths")
    post_parser.set_defaults(func=cmd_post)
    
    # delete (NEW)
    delete_parser = subparsers.add_parser("delete", help="Delete a note")
    delete_parser.add_argument("note_id", help="Note ID or URL")
    delete_parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    delete_parser.set_defaults(func=cmd_delete)
    
    # notifications (NEW)
    notifications_parser = subparsers.add_parser("notifications", help="Get notifications")
    notifications_parser.add_argument("--type", choices=["mentions", "likes", "connections"], default="mentions")
    notifications_parser.add_argument("--cursor", default="", help="Pagination cursor")
    notifications_parser.add_argument("--num", type=int, default=20, help="Number of notifications")
    notifications_parser.set_defaults(func=cmd_notifications)
    
    # unread (NEW)
    unread_parser = subparsers.add_parser("unread", help="Get unread notification count")
    unread_parser.set_defaults(func=cmd_unread)
    
    return parser


def handle_xhs_command(args: list[str]) -> int:
    """Main entry point for wr xhs command."""
    parser = create_parser()
    parsed_args = parser.parse_args(args)
    
    if not parsed_args.command:
        parser.print_help()
        return 1
    
    return parsed_args.func(parsed_args)


if __name__ == "__main__":
    sys.exit(handle_xhs_command(sys.argv[1:]))

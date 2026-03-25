"""Helpers for resolving and persisting note references across commands."""

from __future__ import annotations

import re
from typing import Optional, Tuple

from .cookies import get_note_by_index, save_note_index


def parse_note_reference(ref: str) -> Tuple[str, str, str]:
    """
    Parse a note reference from URL or note ID.
    
    Args:
        ref: URL like https://www.xiaohongshu.com/explore/xxx or note ID
        
    Returns:
        Tuple of (note_id, xsec_token, xsec_source)
    """
    note_id = ""
    xsec_token = ""
    xsec_source = ""
    
    # Check if it's a URL
    if ref.startswith(("http://", "https://")):
        # Extract note_id from URL
        match = re.search(r"/explore/([a-zA-Z0-9]+)", ref)
        if match:
            note_id = match.group(1)
        
        # Extract xsec_token from URL query
        token_match = re.search(r"[?&]xsec_token=([^&]+)", ref)
        if token_match:
            xsec_token = token_match.group(1)
        
        # Extract xsec_source from URL query
        source_match = re.search(r"[?&]xsec_source=([^&]+)", ref)
        if source_match:
            xsec_source = source_match.group(1)
    else:
        # Treat as note ID
        note_id = ref.strip()
    
    return note_id, xsec_token, xsec_source


def resolve_note_reference(id_or_url: str, *, xsec_token: str = "") -> Tuple[str, str, str]:
    """Resolve a note reference from URL/ID or the last listing index."""
    # Check if it's a numeric index
    if id_or_url.isdigit():
        entry = get_note_by_index(int(id_or_url))
        if entry is None:
            raise ValueError(
                f"Index {id_or_url} not found — run a listing command first "
                "(search / feed / hot / user-posts / favorites / my-notes)"
            )
        return (
            entry["note_id"],
            xsec_token or entry.get("xsec_token", ""),
            entry.get("xsec_source", ""),
        )

    note_id, url_token, url_source = parse_note_reference(id_or_url)
    return note_id, xsec_token or url_token, url_source


def save_index_from_items(data: dict, *, xsec_source: str) -> None:
    """Persist ordered note references from list-style responses."""
    entries = []
    for item in data.get("items", []):
        note_card = item.get("note_card", {})
        note_id = item.get("id", note_card.get("note_id", ""))
        token = item.get("xsec_token", note_card.get("xsec_token", ""))
        if note_id:
            entries.append({
                "note_id": note_id,
                "xsec_token": token,
                "xsec_source": xsec_source if token else "",
            })
    save_note_index(entries)


def save_index_from_notes(notes: list[dict]) -> None:
    """Persist ordered note references from paged note payloads."""
    save_note_index([
        {
            "note_id": str(note.get("note_id", note.get("id", ""))).strip(),
            "xsec_token": str(note.get("xsec_token", "")).strip(),
            "xsec_source": "",
        }
        for note in notes
        if str(note.get("note_id", note.get("id", ""))).strip()
    ])


def extract_note_id(id_or_url: str) -> str:
    """Extract note ID from URL or return as-is if it's already an ID."""
    note_id, _, _ = parse_note_reference(id_or_url)
    return note_id or id_or_url.strip()

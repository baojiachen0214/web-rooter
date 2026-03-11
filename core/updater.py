"""
CLI updater helpers (GitHub release check + local git checkout update).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SEMVER_TAG_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-._]?([0-9A-Za-z.-]+))?$")


@dataclass
class ReleaseInfo:
    tag_name: str
    name: str
    published_at: str
    prerelease: bool
    draft: bool
    html_url: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tag_name": self.tag_name,
            "name": self.name,
            "published_at": self.published_at,
            "prerelease": self.prerelease,
            "draft": self.draft,
            "html_url": self.html_url,
        }


def parse_semver_tag(tag: str) -> Optional[Tuple[int, int, int, bool, str]]:
    text = str(tag or "").strip()
    match = SEMVER_TAG_PATTERN.match(text)
    if not match:
        return None
    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3))
    suffix = (match.group(4) or "").strip()
    is_prerelease = bool(suffix)
    return major, minor, patch, is_prerelease, suffix


def compare_semver_tags(current_tag: str, candidate_tag: str) -> Optional[int]:
    """
    Compare semantic version tags.

    Returns:
    - 1 when candidate > current
    - 0 when equal
    - -1 when candidate < current
    - None when either tag is non-semver
    """
    current = parse_semver_tag(current_tag)
    candidate = parse_semver_tag(candidate_tag)
    if current is None or candidate is None:
        return None

    cur_core = current[:3]
    cand_core = candidate[:3]
    if cand_core > cur_core:
        return 1
    if cand_core < cur_core:
        return -1

    # Same core version: stable > prerelease
    cur_pre = current[3]
    cand_pre = candidate[3]
    if cur_pre and not cand_pre:
        return 1
    if not cur_pre and cand_pre:
        return -1
    if current[4] == candidate[4]:
        return 0
    # Fallback lexical for prerelease identifiers.
    return 1 if candidate[4] > current[4] else -1


def fetch_github_releases(
    repo: str,
    limit: int = 20,
    include_prerelease: bool = True,
    timeout_sec: float = 12.0,
    token: Optional[str] = None,
) -> List[ReleaseInfo]:
    limit = max(1, min(int(limit), 100))
    endpoint = f"https://api.github.com/repos/{repo}/releases?per_page={limit}"
    auth_token = (token or os.getenv("WEB_ROOTER_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or "").strip()
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "web-rooter-updater",
    }
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    request = Request(
        endpoint,
        headers=headers,
    )
    try:
        with urlopen(request, timeout=timeout_sec) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"github_api_error:{exc}") from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"github_api_parse_error:{exc}") from exc

    if not isinstance(payload, list):
        raise RuntimeError("github_api_invalid_payload")

    releases: List[ReleaseInfo] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        draft = bool(item.get("draft"))
        prerelease = bool(item.get("prerelease"))
        if draft:
            continue
        if prerelease and not include_prerelease:
            continue
        tag_name = str(item.get("tag_name") or "").strip()
        if not tag_name:
            continue
        releases.append(
            ReleaseInfo(
                tag_name=tag_name,
                name=str(item.get("name") or tag_name),
                published_at=str(item.get("published_at") or ""),
                prerelease=prerelease,
                draft=draft,
                html_url=str(item.get("html_url") or ""),
            )
        )
    return releases


def select_latest_release(releases: List[ReleaseInfo]) -> Optional[ReleaseInfo]:
    if not releases:
        return None
    semver_items = []
    for item in releases:
        parsed = parse_semver_tag(item.tag_name)
        if parsed is None:
            continue
        semver_items.append((parsed, item))
    if semver_items:
        semver_items.sort(key=lambda pair: (pair[0][0], pair[0][1], pair[0][2], not pair[0][3], pair[0][4]), reverse=True)
        return semver_items[0][1]
    return releases[0]


def is_git_repo(repo_root: str | Path) -> bool:
    root = Path(repo_root).expanduser().resolve()
    if not (root / ".git").exists():
        return False
    return _run_git(["rev-parse", "--is-inside-work-tree"], cwd=root).returncode == 0


def infer_github_repo_from_git(repo_root: str | Path, remote: str = "origin") -> Optional[str]:
    root = Path(repo_root).expanduser().resolve()
    if not is_git_repo(root):
        return None
    probe = _run_git(["remote", "get-url", remote], cwd=root)
    if probe.returncode != 0:
        return None
    raw = str(probe.stdout or "").strip()
    if not raw:
        return None

    # https://github.com/owner/repo(.git)
    match = re.search(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$", raw)
    if not match:
        return None
    owner = match.group("owner").strip()
    repo = match.group("repo").strip()
    if not owner or not repo:
        return None
    return f"{owner}/{repo}"


def update_git_to_tag(
    repo_root: str | Path,
    tag: str,
    remote: str = "origin",
    allow_dirty: bool = False,
) -> Dict[str, Any]:
    root = Path(repo_root).expanduser().resolve()
    if not is_git_repo(root):
        return {"success": False, "error": "not_git_repo", "repo_root": str(root)}

    status = _run_git(["status", "--porcelain"], cwd=root)
    dirty = bool((status.stdout or "").strip())
    if dirty and not allow_dirty:
        return {
            "success": False,
            "error": "dirty_worktree",
            "repo_root": str(root),
            "hint": "commit_or_stash_first_or_use_force",
        }

    fetch = _run_git(["fetch", remote, "--tags", "--prune"], cwd=root)
    if fetch.returncode != 0:
        return {
            "success": False,
            "error": "git_fetch_failed",
            "stdout": (fetch.stdout or "").strip(),
            "stderr": (fetch.stderr or "").strip(),
        }

    verify = _run_git(["rev-parse", "--verify", f"refs/tags/{tag}"], cwd=root)
    if verify.returncode != 0:
        return {"success": False, "error": f"tag_not_found:{tag}"}

    checkout = _run_git(["checkout", "--detach", tag], cwd=root)
    if checkout.returncode != 0:
        return {
            "success": False,
            "error": "git_checkout_failed",
            "stdout": (checkout.stdout or "").strip(),
            "stderr": (checkout.stderr or "").strip(),
        }

    head = _run_git(["rev-parse", "--short", "HEAD"], cwd=root)
    return {
        "success": True,
        "repo_root": str(root),
        "tag": tag,
        "head": (head.stdout or "").strip(),
        "detached": True,
    }


def _run_git(args: List[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=30,
    )

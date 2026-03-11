from __future__ import annotations

from core.updater import compare_semver_tags, parse_semver_tag, select_latest_release, ReleaseInfo


def test_parse_semver_tag() -> None:
    parsed = parse_semver_tag("v0.2.1")
    assert parsed is not None
    assert parsed[:3] == (0, 2, 1)
    assert parsed[3] is False

    parsed_pre = parse_semver_tag("v0.3.0-alpha.1")
    assert parsed_pre is not None
    assert parsed_pre[:3] == (0, 3, 0)
    assert parsed_pre[3] is True
    assert parsed_pre[4] == "alpha.1"

    assert parse_semver_tag("release-2026-03") is None


def test_compare_semver_tags() -> None:
    assert compare_semver_tags("v0.2.1", "v0.2.2") == 1
    assert compare_semver_tags("v0.2.2", "v0.2.1") == -1
    assert compare_semver_tags("v0.2.1", "v0.2.1") == 0
    assert compare_semver_tags("v0.2.1-alpha", "v0.2.1") == 1
    assert compare_semver_tags("v0.2.1", "v0.2.1-alpha") == -1
    assert compare_semver_tags("main", "v0.2.1") is None


def test_select_latest_release_prefers_highest_semver() -> None:
    releases = [
        ReleaseInfo(
            tag_name="v0.2.1",
            name="0.2.1",
            published_at="2026-03-01T00:00:00Z",
            prerelease=False,
            draft=False,
            html_url="https://example.com/1",
        ),
        ReleaseInfo(
            tag_name="v0.3.0-alpha",
            name="0.3.0-alpha",
            published_at="2026-03-02T00:00:00Z",
            prerelease=True,
            draft=False,
            html_url="https://example.com/2",
        ),
        ReleaseInfo(
            tag_name="v0.2.2",
            name="0.2.2",
            published_at="2026-03-03T00:00:00Z",
            prerelease=False,
            draft=False,
            html_url="https://example.com/3",
        ),
    ]
    latest = select_latest_release(releases)
    assert latest is not None
    assert latest.tag_name == "v0.3.0-alpha"


def test_select_latest_release_returns_none_on_empty() -> None:
    assert select_latest_release([]) is None

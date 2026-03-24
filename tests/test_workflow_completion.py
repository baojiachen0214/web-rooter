from core.workflow_completion import evaluate_completion_contract


def test_completion_contract_reports_partial_when_comments_missing() -> None:
    payload = {
        "steps": {
            "auth_hint": {"success": True},
            "read_target": {
                "success": True,
                "data": {
                    "platform": "xiaohongshu",
                    "fetch_mode": "browser_xiaohongshu_specialized",
                    "note_detail": {
                        "title": "标题",
                        "body": "正文内容",
                        "author_name": "作者",
                        "liked_count": "10",
                    },
                    "comments": [],
                },
            },
            "extract_social_signals": {
                "success": True,
                "data": {"extracted": "标题：标题\n作者：作者\n正文：正文内容"},
            },
        },
        "reports": [
            {"id": "auth_hint", "status": "completed"},
            {"id": "read_target", "status": "completed"},
            {"id": "extract_social_signals", "status": "completed"},
        ],
    }
    contract = {
        "required_outputs": ["body", "author", "engagement", "comments"],
        "quality_gates": {"comment_capture_preferred": True, "browser_required": True, "auth_hint_checked": True},
        "fallback_chain": ["xhs_xhr_capture", "xhs_dom_comments"],
    }
    report = evaluate_completion_contract(payload, contract)
    assert report["status"] == "partial"
    assert report["completion_percent"] == 75
    assert report["missing_outputs"] == ["comments"]
    assert report["should_fallback"] is True


def test_completion_contract_reports_complete_when_all_outputs_present() -> None:
    payload = {
        "steps": {
            "auth_hint": {"success": True},
            "read_target": {
                "success": True,
                "data": {
                    "platform": "bilibili",
                    "fetch_mode": "browser_bilibili_specialized",
                    "video_detail": {
                        "title": "视频标题",
                        "body": "简介",
                        "author_name": "UP主",
                        "view_count": "1000",
                        "reply_count": "5",
                    },
                    "comments": [{"comment_id": "c1", "content": "好看"}],
                },
            },
        },
        "reports": [{"id": "read_target", "status": "completed"}],
    }
    contract = {
        "required_outputs": ["body", "author", "engagement", "comments"],
        "quality_gates": {"comment_capture_preferred": True, "browser_required": True},
    }
    report = evaluate_completion_contract(payload, contract)
    assert report["status"] == "complete"
    assert report["completion_percent"] == 100
    assert report["missing_outputs"] == []

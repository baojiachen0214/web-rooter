from core.social.bilibili_reader import (
    extract_bilibili_video_ref,
    extract_video_detail_from_state,
    is_bilibili_detail_url,
    is_bilibili_video_url,
    normalize_bilibili_comments_from_payload,
    normalize_bilibili_video_detail,
    parse_bilibili_initial_state,
)


def test_extract_bilibili_video_ref_from_url() -> None:
    ref = extract_bilibili_video_ref("https://www.bilibili.com/video/BV1xx411c7mD/")
    assert ref["bvid"] == "BV1xx411c7mD"
    assert ref["url"].startswith("https://www.bilibili.com/video/")


def test_bilibili_url_detection() -> None:
    assert is_bilibili_video_url("https://www.bilibili.com/video/BV1xx411c7mD/") is True
    assert is_bilibili_detail_url("https://www.bilibili.com/video/BV1xx411c7mD/") is True
    assert is_bilibili_detail_url("https://b23.tv/abcdEF") is True


def test_parse_bilibili_initial_state_and_normalize_detail() -> None:
    html = '''
    <html><body>
    <script>window.__INITIAL_STATE__={
      "videoData": {
        "bvid": "BV1xx411c7mD",
        "aid": 123,
        "title": "测试视频",
        "desc": "这里是简介",
        "owner": {"name": "测试UP", "mid": 42},
        "stat": {"view": 1000, "reply": 12, "like": 55, "danmaku": 9}
      }
    };</script>
    </body></html>
    '''
    state = parse_bilibili_initial_state(html)
    detail = extract_video_detail_from_state(state, bvid="BV1xx411c7mD")
    assert detail["title"] == "测试视频"
    assert detail["author_name"] == "测试UP"
    assert detail["reply_count"] == "12"

    normalized = normalize_bilibili_video_detail(state["videoData"], bvid="BV1xx411c7mD")
    assert normalized["bvid"] == "BV1xx411c7mD"
    assert normalized["body"] == "这里是简介"


def test_normalize_bilibili_comments_from_payload() -> None:
    payload = {
        "data": {
            "replies": [
                {
                    "rpid_str": "c1",
                    "member": {"uname": "甲", "mid": "u1"},
                    "content": {"message": "主评论"},
                    "like": 8,
                    "replies": [
                        {
                            "rpid_str": "c2",
                            "member": {"uname": "乙", "mid": "u2"},
                            "content": {"message": "楼中楼"},
                            "like": 2,
                        }
                    ],
                }
            ]
        }
    }
    comments = normalize_bilibili_comments_from_payload(payload)
    assert [item["comment_id"] for item in comments] == ["c1", "c2"]
    assert comments[0]["content"] == "主评论"
    assert comments[1]["root_comment_id"] == "c1"

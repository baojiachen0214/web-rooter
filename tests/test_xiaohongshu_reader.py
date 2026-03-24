from agents.web_agent import WebAgent
from core.social.xiaohongshu_reader import (
    extract_note_detail_from_feed_payload,
    extract_xiaohongshu_note_ref,
    normalize_comments_from_payload,
    normalize_note_detail,
    parse_initial_state,
)


def test_extract_xiaohongshu_note_ref_from_url():
    ref = extract_xiaohongshu_note_ref(
        "https://www.xiaohongshu.com/explore/abc123xyz?xsec_token=token123&xsec_source=pc_search"
    )
    assert ref["note_id"] == "abc123xyz"
    assert ref["xsec_token"] == "token123"
    assert ref["xsec_source"] == "pc_search"


def test_parse_initial_state_and_normalize_note_detail():
    html = '''
    <html><head></head><body>
    <script>window.__INITIAL_STATE__={"note":{"noteDetailMap":{"abc123":{"note":{
      "note_id":"abc123",
      "title":"测试标题",
      "desc":"这里是正文内容",
      "user":{"nickname":"测试作者","user_id":"u1"},
      "interact_info":{"liked_count":"12","comment_count":"7","collected_count":"3"},
      "tag_list":[{"name":"测评"},{"name":"手机"}]
    }}}}}</script>
    </body></html>
    '''
    state = parse_initial_state(html)
    note = normalize_note_detail(state["note"]["noteDetailMap"]["abc123"]["note"], note_id="abc123")
    assert note["title"] == "测试标题"
    assert note["body"] == "这里是正文内容"
    assert note["author_name"] == "测试作者"
    assert note["comment_count"] == "7"
    assert note["tags"] == ["测评", "手机"]


def test_extract_feed_detail_and_comments_normalization():
    feed_payload = {
        "data": {
            "items": [
                {
                    "id": "abc123",
                    "xsec_token": "tok",
                    "xsec_source": "pc_feed",
                    "note_card": {
                        "note_id": "abc123",
                        "title": "标题",
                        "desc": "正文",
                        "user": {"nickname": "作者", "user_id": "u1"},
                        "interact_info": {"comment_count": "2"},
                    },
                }
            ]
        }
    }
    detail = extract_note_detail_from_feed_payload(feed_payload, note_id="abc123")
    assert detail["note_id"] == "abc123"
    assert detail["xsec_token"] == "tok"
    assert detail["body"] == "正文"

    comments_payload = {
        "data": {
            "comments": [
                {
                    "id": "c1",
                    "content": "主评论",
                    "user_info": {"nickname": "甲", "user_id": "u1"},
                    "sub_comments": [
                        {
                            "id": "c2",
                            "content": "回复评论",
                            "user_info": {"nickname": "乙", "user_id": "u2"},
                        }
                    ],
                }
            ]
        }
    }
    comments = normalize_comments_from_payload(comments_payload)
    assert [item["comment_id"] for item in comments] == ["c1", "c2"]
    assert comments[0]["content"] == "主评论"
    assert comments[1]["root_comment_id"] == "c1"


def test_social_route_prefers_direct_detail_url_spec():
    agent = WebAgent()
    route, spec = agent._build_default_orchestration_spec(
        task="分析这个小红书帖子正文和评论区 https://www.xiaohongshu.com/explore/abc123?xsec_token=tok",
        html_first=True,
        top_results=5,
        use_browser=False,
        crawl_assist=False,
        crawl_pages=2,
    )
    assert route == "social"
    assert spec["name"] == "direct-social-detail-analysis"
    assert spec["variables"]["use_browser"] is True
    assert spec["variables"]["platforms"] == ["xiaohongshu"]
    assert [step["id"] for step in spec["steps"]] == ["auth_hint", "read_target", "extract_social_signals"]

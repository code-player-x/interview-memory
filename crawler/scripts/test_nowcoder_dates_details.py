"""Regression tests for source dates and post-only SSR extraction; no network."""
from datetime import datetime, timezone
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
import urllib.request

import httpx
import nowcoder_details
import nowcoder_harvest
from nowcoder_scan_window import scan

from nowcoder_harvest import extract_post, in_date_range, load_config
from nowcoder_details import extract_detail


def millis(iso):
    return int(datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp() * 1000)


def ssr(content, **extra):
    common = {"contentData": content, **extra}
    return "<script>window.__INITIAL_STATE__=" + json.dumps({"prefetchData": {"2": {"ssrCommonData": common}}}) + ";</script>"


class SourceDateTests(unittest.TestCase):
    def test_created_at_wins_over_edit_and_author_times(self):
        record = {"data": {
            "contentId": "1", "userBrief": {"memberStartTime": millis("2026-11-17T00:00:00")},
            "momentData": {"id": 1, "uuid": "source-uuid", "title": "面经", "content": "问题",
                           "editTime": millis("2026-11-18T00:00:00"),
                           "createdAt": millis("2026-09-17T16:30:00")},
        }}
        post = extract_post(record, "AI Infra 面经")
        self.assertEqual(post["date"], "2026-09-18")  # Beijing day, not UTC day.
        self.assertEqual(post["date_field"], "createdAt")
        self.assertEqual(post["url"], "https://www.nowcoder.com/feed/main/detail/source-uuid")

    def test_unknown_creation_is_not_inferred_from_edit_or_user(self):
        post = extract_post({"data": {"contentId": "2", "userBrief": {"createTime": millis("2026-10-01T00:00:00")},
                                     "momentData": {"id": 2, "title": "面经", "editTime": millis("2026-10-02T00:00:00")}}}, "x")
        self.assertEqual(post["date"], "")
        self.assertIsNone(post["date_field"])

    def test_content_data_takes_precedence_over_interview_badge(self):
        post = extract_post({"data": {"contentId": "900", "interviewExp": {"message": "查看真题"},
                                     "contentData": {"id": "900", "title": "推理面经", "content": "<p>KV cache 如何管理？</p>",
                                                     "createTime": millis("2026-10-01T00:00:00")}}}, "vLLM 面经")
        self.assertEqual(post["title"], "推理面经")
        self.assertIn("KV cache", post["text"])
        self.assertEqual(post["date"], "2026-10-01")
        self.assertEqual(post["url"], "https://www.nowcoder.com/discuss/900")

    def test_date_window_is_inclusive_and_rejects_unknown(self):
        config = {"date_from": "2026-09-18", "date_to": "2026-11-18"}
        for value, expected in [("2026-09-17", False), ("2026-09-18", True),
                                ("2026-10-01", True), ("2026-11-18", True),
                                ("2026-11-19", False), ("", False), (None, False)]:
            with self.subTest(value=value):
                self.assertEqual(in_date_range({"date": value}, config), expected)
        self.assertTrue(in_date_range({}, {}))

    def test_invalid_or_reversed_config_dates_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            for dates in ({"date_from": "2026-02-30"}, {"date_from": "2026-11-19", "date_to": "2026-11-18"}):
                path.write_text(json.dumps({"queries": ["AI Infra 面经"], **dates}), encoding="utf-8")
                with self.subTest(dates=dates), self.assertRaises(ValueError):
                    load_config(path)


class DetailExtractionTests(unittest.TestCase):
    def setUp(self):
        self.row = {"id": "1", "url": "https://www.nowcoder.com/feed/main/detail/source-uuid"}

    def test_rich_text_main_post_only_with_original_creation(self):
        page = ssr({"id": 1, "uuid": "source-uuid", "title": "主帖",
                    "richText": "<p>如何优化推理？</p><p>如何定位通信瓶颈？</p>", "content": "摘要",
                    "createdAt": millis("2026-09-17T16:30:00"),
                    "editTime": millis("2026-11-18T00:00:00"),
                    "userBrief": {"createTime": millis("2026-10-01T00:00:00")}},
                   commentListFirst=[{"content": "评论不能混入正文"}], similarRecommend=[{"content": "推荐不能混入正文"}])
        result = extract_detail(page, self.row)
        self.assertEqual(result["detail_status"], "full_text")
        self.assertEqual(result["detail_date"], "2026-09-18")
        self.assertEqual(result["detail_date_field"], "createdAt")
        self.assertEqual([line.strip() for line in result["detail_text"].splitlines()],
                         ["如何优化推理？", "如何定位通信瓶颈？"])

    def test_uuid_is_a_valid_identity(self):
        result = extract_detail(ssr({"id": 999, "uuid": "source-uuid", "content": "主帖内容"}), self.row)
        self.assertEqual(result["detail_text"], "主帖内容")

    def test_off_origin_source_is_rejected_before_public_or_browser_request(self):
        with patch("urllib.request.urlopen") as cdp, patch("urllib.request.build_opener") as public:
            for url in ["https://example.invalid/post", "http://www.nowcoder.com/post",
                        "https://www.nowcoder.com:444/post", "https://user@www.nowcoder.com/post"]:
                with self.subTest(url=url):
                    for fetch in (nowcoder_details.public_fetch, nowcoder_details.cdp_fetch):
                        with self.assertRaisesRegex(ValueError, "仅允许牛客"):
                            fetch(url)
            public.assert_not_called()
            cdp.assert_not_called()

    def test_public_redirect_validates_destination_before_following(self):
        handler = nowcoder_details.NowcoderRedirect()
        request = urllib.request.Request(self.row["url"])
        redirected = handler.redirect_request(request, None, 302, "", {}, "https://www.nowcoder.com/discuss/1")
        self.assertEqual(redirected.full_url, "https://www.nowcoder.com/discuss/1")
        with self.assertRaisesRegex(ValueError, "仅允许牛客"):
            handler.redirect_request(request, None, 302, "", {}, "https://example.invalid/")

    def test_browser_fetch_restricts_request_to_same_origin_and_stops_redirects(self):
        listing = MagicMock()
        listing.__enter__.return_value.read.return_value = json.dumps([
            {"type": "page", "url": "https://www.nowcoder.com/", "webSocketDebuggerUrl": "test-page"},
        ]).encode()
        send = MagicMock(return_value=1)
        wait = MagicMock(return_value={"result": {"result": {"value": "page"}}})
        with patch("urllib.request.urlopen", return_value=listing), patch("websocket.create_connection"), \
                patch.object(nowcoder_details, "make_rpc", return_value=(send, wait)):
            self.assertEqual(nowcoder_details.cdp_fetch(self.row["url"]), "page")
        expression = send.call_args.args[1]["expression"]
        self.assertIn("mode:'same-origin'", expression)
        self.assertIn("redirect:'error'", expression)

    def test_mismatched_ssr_id_is_rejected(self):
        with self.assertRaises(ValueError):
            extract_detail(ssr({"id": 999, "uuid": "other", "content": "无关帖子"}), self.row)

    def test_missing_creation_and_image_only_are_explicit(self):
        result = extract_detail(ssr({"id": 1, "content": "", "editTime": millis("2026-11-18T00:00:00"),
                                     "imgMoment": [{"src": "https://example.test/image.png"}]}), self.row)
        self.assertEqual(result["detail_status"], "image_only")
        self.assertEqual(result["detail_text"], "")
        self.assertNotIn("detail_date", result)


class SnapshotTests(unittest.TestCase):
    def test_scan_binds_checkpoints_to_window_and_preserves_legacy_results(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
                "success": True, "data": {"records": [], "total": 0, "totalPage": 0},
            }))
            client = httpx.Client
            with patch("nowcoder_scan_window.httpx.Client", side_effect=lambda **kw: client(transport=transport, **kw)), \
                    patch("nowcoder_scan_window.time.sleep"):
                first = scan(output, ["GPU"], "2026-09-18", "2026-11-18")
                self.assertEqual(first, scan(output, ["GPU"], "2026-09-18", "2026-11-18"))
            log = output / "page-log.jsonl"
            before = log.read_bytes()
            with self.assertRaisesRegex(ValueError, "日期窗口不同"):
                scan(output, ["GPU"], "2026-08-18", "2026-11-18")
            (output / "scan-window.json").unlink()
            with self.assertRaisesRegex(ValueError, "旧扫描"):
                scan(output, ["GPU"], "2026-09-18", "2026-11-18")
            self.assertEqual(log.read_bytes(), before)

    def test_harvest_applies_current_config_to_historical_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "posts.jsonl"
            config = Path(folder) / "config.json"
            config.write_text(json.dumps({"queries": ["GPU"], "pages": 1, "include_patterns": ["GPU"],
                                          "date_from": "2026-09-18"}), encoding="utf-8")
            records = [
                {"id": "old", "title": "", "date": "2026-09-17", "text": "GPU" * 20},
                {"id": "unrelated", "title": "", "date": "2026-09-19", "text": "x" * 60},
                {"id": "good", "title": "GPU", "date": "2026-09-19", "text": "x" * 60},
            ]
            output.write_text("\n".join(json.dumps(row) for row in records), encoding="utf-8")
            args = ["nowcoder", "--config", str(config), "--output", str(output)]
            with patch("sys.argv", args), patch.object(nowcoder_harvest, "connect"), \
                    patch.object(nowcoder_harvest, "make_rpc", return_value=(MagicMock(), MagicMock())), \
                    patch.object(nowcoder_harvest, "fetch_search", return_value={"success": True}), \
                    patch.object(nowcoder_harvest.time, "sleep"):
                nowcoder_harvest.main()
            self.assertEqual([json.loads(line)["id"] for line in output.read_text("utf-8").splitlines()], ["good"])


if __name__ == "__main__":
    unittest.main()

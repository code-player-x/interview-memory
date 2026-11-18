"""Public listing parser and index regression checks."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import onepoint3acres_harvest as forum


class ForumIndexTests(unittest.TestCase):
    def test_index_deduplicates_and_preserves_history_on_error(self):
        page = """
        <table id="threadlisttableid">
        <tbody id="normalthread_25"><tr><th class="common">
        <a href="thread-25-1-1.html">打开帖子</a>
        <a class="s xst" href="forum.php?mod=viewthread&amp;tid=25">GPU <em>Inference</em> 面经</a>
        <a href="thread-25-1-1.html">4</a>
        </th></tr></tbody>
        <tbody id="normalthread_28"><tr><th>
        <a class="s xst" href="thread-28-1-1.html">General SWE</a>
        <a class="s xst" href="https://other.example/bbs/thread-30-1-1.html">GPU ad</a>
        </th></tr></tbody></table>
        <aside><a class="s xst" href="thread-42-1-1.html">GPU sale</a></aside>
        """
        with TemporaryDirectory() as directory:
            out = Path(directory) / "index.jsonl"
            forum.update_index([page], ["gpu"], out)
            forum.update_index([page], ["GPU"], out)
            rows = [json.loads(line) for line in out.read_text("utf-8").splitlines()]
            self.assertEqual([row["id"] for row in rows], ["25"])
            self.assertEqual(rows[0]["title"], "GPU Inference 面经")
            self.assertEqual(rows[0]["url"], forum.SITE + "/bbs/thread-25-1-1.html")
            previous = out.read_bytes()
            for invalid in (
                '<h1>请登录</h1><aside><a class="s xst" href="thread-42-1-1.html">GPU sale</a></aside>',
                '<table id="threadlisttableid"></table>',
                '<table id="threadlisttableid"><tr><td><a href="thread-42-1-1.html">GPU</a></td></tr></table>',
            ):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    forum.update_index([page, invalid], ["gpu"], out)
                self.assertEqual(out.read_bytes(), previous)

    def test_robots_wildcard_denies_listing_before_request(self):
        with patch.object(forum, "fetch", return_value="User-agent: *\nDisallow: /bbs/*") as fetch:
            with self.assertRaisesRegex(ValueError, "robots"):
                list(forum.online_pages(1))
            fetch.assert_called_once_with(forum.SITE + "/robots.txt", robots=True)


if __name__ == "__main__":
    unittest.main()

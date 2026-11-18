import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import github_harvest as github


def blob_sha(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


class GitHubHarvestTest(unittest.TestCase):
    def test_limited_runs_resume_and_changed_files_replace_previous_version(self):
        blobs = {"面试题.md": b"# title\na", "README.md": b"# title\nb"}
        fetched = []

        def fake_api(endpoint, accept=None, limit=None):
            if endpoint.endswith("/commits/HEAD"):
                return (b"2" if blobs["面试题.md"].endswith(b"c") else b"1") * 40
            if "/trees/" in endpoint:
                return {"truncated": False, "tree": [
                    {"path": path, "mode": "100644", "type": "blob", "sha": blob_sha(raw), "size": len(raw)}
                    for path, raw in blobs.items()
                ]}
            raw = next(raw for raw in blobs.values() if endpoint.endswith(blob_sha(raw)))
            fetched.append(raw)
            return raw

        with TemporaryDirectory() as folder, patch.object(github, "api", fake_api), \
                patch.dict("os.environ", {"GITHUB_TOKEN": ""}):
            output = Path(folder) / "posts.jsonl"
            cli = ["--repo", "owner/book", "--max-files", "1", "--output", str(output)]
            for _ in range(3):
                self.assertEqual(github.main(cli), 0)
            self.assertEqual(fetched, [b"# title\na", b"# title\nb"])
            blobs["面试题.md"] = b"# title\nc"
            self.assertEqual(github.main(cli), 0)
            rows = [json.loads(line) for line in output.read_text("utf-8").splitlines()]
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["text"], "# title\nc")
            self.assertIn("/blob/" + "2" * 40 + "/%", rows[0]["url"])

    def test_truncated_download_retries_legacy_row_and_verifies_raw_bytes(self):
        # Verify before utf-8-sig strips the BOM.
        raw = b"\xef\xbb\xbf# title"
        sha = blob_sha(raw)
        key = "owner/book:doc.md"
        rows = {key: {"repo": "owner/book", "blob_sha": sha, "text": "old partial"}}
        entries = [("doc.md", sha, len(raw))]
        with patch.dict("os.environ", {"GITHUB_TOKEN": ""}), \
                patch.object(github, "markdown_files", return_value=entries), \
                patch.object(github, "api", side_effect=[b"1"*40, raw[:-1], b"1"*40, raw]):
            with self.assertRaisesRegex(ValueError, "SHA"):
                github.harvest_repo("owner/book", rows, 10, 100, None)
            self.assertEqual(rows[key]["text"], "old partial")
            github.harvest_repo("owner/book", rows, 10, 100, None)
        self.assertEqual(rows[key]["text"], "# title")
        self.assertTrue(rows[key]["blob_verified"])

    def test_prune_only_after_complete_walk_for_this_repo(self):
        raw = b"new name"
        sha = blob_sha(raw)
        rows = {
            "org/doc:old.md": {"repo": "org/doc", "blob_sha": sha},
            "org/doc:big.md": {"repo": "org/doc", "blob_sha": "b"*40},
            "org/other:old.md": {"repo": "org/other", "blob_sha": sha},
        }
        files = [("new.md", sha, len(raw)), ("big.md", "b"*40, 1000)]
        with patch.dict("os.environ", {"GITHUB_TOKEN": ""}), \
                patch.object(github, "markdown_files", return_value=files), \
                patch.object(github, "api", side_effect=[b"1"*40, raw, b"1"*40]):
            github.harvest_repo("org/doc", rows, 1, 100, None)
            self.assertIn("org/doc:old.md", rows)
            github.harvest_repo("org/doc", rows, 1, 100, None)
        self.assertEqual(set(rows), {"org/doc:new.md", "org/doc:big.md", "org/other:old.md"})

    def test_partial_run_remains_readable_after_rate_limit(self):
        def interrupted(repo, rows, max_files, max_bytes, cache):
            rows["first"] = {"id": "first", "text": "partial"}
            raise github.RateLimitError()

        with TemporaryDirectory() as folder, patch.object(github, "harvest_repo", interrupted):
            output = Path(folder) / "posts.jsonl"
            with self.assertRaises(github.RateLimitError):
                github.main(["--output", str(output)])
            self.assertEqual(json.loads(output.read_text("utf-8"))["id"], "first")


if __name__ == "__main__":
    unittest.main()

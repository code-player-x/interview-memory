"""Exercise the browser's URL allow-list without loading the full DOM app."""

import shutil
import subprocess
from pathlib import Path

import pytest


APP_JS = Path(__file__).resolve().parents[1] / "frontend" / "app.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is unavailable")
def test_uploaded_local_image_url_is_allowed_without_opening_other_paths():
    script = r"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync(process.argv[1], "utf8");
const start = source.indexOf("function _safeUrl(u) {");
const end = source.indexOf("function _safeUrlAttr(u) {", start);
if (start < 0 || end < 0) throw new Error("_safeUrl not found");
const safeUrl = vm.runInNewContext(source.slice(start, end) + "; _safeUrl");
const name = "a".repeat(32) + ".png";
const cases = [
  ["/data/images/" + name, "/data/images/" + name],
  ["/data/images/../wrong_book_export.pdf", "#"],
  ["/data/wrong_book_export.pdf", "#"],
  ["javascript:alert(1)", "#"],
  ["https://example.com/image.png", "https://example.com/image.png"],
];
for (const [input, expected] of cases) {
  if (safeUrl(input) !== expected) throw new Error(input + " => " + safeUrl(input));
}
"""
    subprocess.run(["node", "-e", script, str(APP_JS)], check=True)

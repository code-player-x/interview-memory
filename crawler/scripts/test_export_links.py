"""Published study guides must be usable without the local collection workspace."""
from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit


class ExportLinksTests(unittest.TestCase):
    def test_relative_links_resolve_with_only_published_exports_available(self):
        exports = Path(__file__).resolve().parents[1] / "exports"
        documents = {doc.resolve(): doc.read_text(encoding="utf-8") for doc in exports.glob("*.md")}
        self.assertTrue(documents)
        for doc, body in documents.items():
            for destination in re.findall(r"\]\(([^)]+)\)", body):
                url = urlsplit(destination.strip("<>"))
                if url.scheme or url.netloc:
                    continue
                target = (doc.parent / unquote(url.path)).resolve() if url.path else doc
                self.assertTrue(target in documents, f"{doc.name} links to unpublished {destination}")
                if url.fragment:
                    anchor = unquote(url.fragment)
                    content = documents[target]
                    self.assertTrue(f'id="{anchor}"' in content or
                                    re.search(r"^#+ " + re.escape(anchor) + r" *$", content, re.M),
                                    f"{doc.name} links to missing anchor {destination}")

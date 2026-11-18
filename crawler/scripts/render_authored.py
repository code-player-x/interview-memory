#!/usr/bin/env python3
"""Compatibility entry point for the single reviewed questions_v2 renderer.

Run from any working directory with ``python crawler/scripts/render_authored.py``.
The curated authored JSONL and generated Markdown remain managed by
``questions_v2/curate_full_v2.py``; this wrapper must not render them a
second, incompatible way.
"""

from __future__ import annotations

import sys
from pathlib import Path


QUESTIONS_V2 = Path(__file__).resolve().parents[1] / "questions_v2"
if str(QUESTIONS_V2) not in sys.path:
    sys.path.insert(0, str(QUESTIONS_V2))

from curate_full_v2 import main  # noqa: E402


if __name__ == "__main__":
    main()

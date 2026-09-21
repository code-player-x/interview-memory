#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""以 UTF-8 捕获任意脚本的 stdout/stderr 到文件（绕开 Windows 控制台 GBK/UTF-16 问题）。

用法：python runner_utf8.py <目标脚本> <输出文件> [脚本参数...]
"""
import io
import pathlib
import runpy
import sys
import traceback

target = sys.argv[1]
outfile = sys.argv[2]
script_args = sys.argv[3:]

buf = io.StringIO()
old_out, old_err = sys.stdout, sys.stderr
sys.stdout = sys.stderr = buf
sys.argv = [target] + script_args
code = 0
try:
    runpy.run_path(target, run_name="__main__")
except SystemExit as e:
    code = e.code or 0
except Exception:
    traceback.print_exc(file=buf)
    code = 1
finally:
    sys.stdout, sys.stderr = old_out, old_err

text = buf.getvalue()
pathlib.Path(outfile).write_text(text, encoding="utf-8")
print(f"[runner] exit={code} wrote {len(text)} chars -> {outfile}")

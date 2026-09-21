#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""parse_node.py — 从 lark-cli 输出文件里抠出 JSON 并打印 obj_token node_token url。
容忍进度文本（Creating wiki node...）混在前后。"""
import json
import sys

txt = open(sys.argv[1], encoding="utf-8", errors="replace").read()
s = txt.find("{")
e = txt.rfind("}")
d = json.loads(txt[s : e + 1])
dd = d.get("data", {})
print(dd.get("obj_token", ""), dd.get("node_token", ""), dd.get("url", ""))

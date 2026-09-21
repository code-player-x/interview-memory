#!/usr/bin/env bash
# upload_fine_categories.sh — 按「计算机面试题题库」细分类目上传（每分类一个飞书文档）
#
# 流程：
#   1) gen_fine_plan.py → data/tmp/fine_category_plan.tsv + fine_*.xml
#   2) 循环每个分类：node-create(NEW) / docs+update(已有/新建) → 写入内容
#      大分类自动分片(overwrite片0 + append片N)，同 upload_feishu.sh 逻辑
#   3) 回写 fine_category_results.tsv → wiki-config.json (新结构)
#
# 用法：
#   bash scripts/upload_fine_categories.sh              # 全量
#   bash scripts/upload_fine_categories.sh --only Golang # 单分类验证
set -uo pipefail

BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BASE"

PY="C:/Users/UserName/.workbuddy/binaries/python/versions/3.13.12/python.exe"
SPACE_ID="7662025183418387409"
GATE=150000
CHUNKS=100000

echo ">> 1/3 生成细分类 XML 与计划"
"$PY" scripts/gen_fine_plan.py "$@"

PLAN="data/tmp/fine_category_plan.tsv"
if [ ! -s "$PLAN" ]; then echo "没有待上传的细分类计划，结束。"; exit 0; fi

sanitize_name() {
  "$PY" -c "import sys; sys.path.insert(0,'scripts'); from split_cat_xml import sanitize; print(sanitize(sys.argv[1]))" "$1"
}

upload_one() {
  local cat="$1" doc_token="$2" title="$3" xmlpath="$4" needs_create="$5"
  local obj="$doc_token" san url

  if [ "$needs_create" = "1" ]; then
    echo "[新建] $cat (space=$SPACE_ID)"
    local nodejson="data/tmp/finenode_${cat}.json"
    lark-cli wiki +node-create --space-id "$SPACE_ID" --title "$title" --as user --format json > "$nodejson" 2>&1
    read obj node url < <("$PY" scripts/parse_node.py "$nodejson")
    if [ -z "$obj" ]; then echo "[FAIL] $cat (node-create)"; cat "$nodejson"; return 1; fi
  else
    echo "[改写] $cat -> $doc_token"
  fi

  local size
  size=$(wc -m < "$xmlpath" | tr -d ' ')
  san=$(sanitize_name "$cat")

  if [ "$size" -le "$GATE" ]; then
    local ok=0 a
    for a in 1 2 3; do
      cat "$xmlpath" | lark-cli docs +update --doc "$obj" --command overwrite --content - --as user --format json > "data/tmp/upd_fine_${san}.log" 2>&1
      if grep -q '"ok": true' "data/tmp/upd_fine_${san}.log"; then ok=1; break; fi
      echo "  $cat overwrite attempt $a failed"; sleep 6
    done
    [ $ok -eq 0 ] && { echo "[FAIL] $cat (overwrite)"; return 1; }
  else
    local nparts=$(( (size + CHUNKS - 1) / CHUNKS ))
    echo "  $cat large(${size}chars), splitting into ${nparts} parts"
    "$PY" scripts/split_cat_xml.py_fine "$cat" "$nparts" >/dev/null 2>&1 || \
    "$PY" -c "
import sys; sys.path.insert(0,'scripts')
from split_cat_xml import *
cat_name=sys.argv[1]; n=int(sys.argv[2])
p=os.path.join('data/tmp',f'fine_{sanitize(cat_name)}.xml')
split_xml(p, cat_name, n, 'fine_')
" "$cat" "$nparts"
    local i=0
    while [ -f "data/tmp/fine_${san}_part${i}.xml" ]; do
      local cmd="overwrite"; [ "$i" -gt 0 ] && cmd="append"
      local f="data/tmp/fine_${san}_part${i}.xml" lok=0 a
      for a in 1 2 3 4; do
        cat "$f" | lark-cli docs +update --doc "$obj" --command "$cmd" --content - --as user --format json > "data/tmp/upd_fine_${san}_p${i}.log" 2>&1
        if grep -q '"ok": true' "data/tmp/upd_fine_${san}_p${i}.log"; then lok=1; break; fi
        echo "  $cat part${i}($cmd) attempt $a failed"; sleep 6
      done
      [ $lok -eq 0 ] && { echo "[FAIL] $cat part${i}"; return 1; }
      i=$((i+1))
    done
  fi

  url="https://my.feishu.cn/wiki/$obj"
  echo "[OK] $cat -> $url"
  printf '%s\t%s\t%s\t%s\n' "$cat" "$obj" "$url" "$([ "$needs_create" = "1" ] && echo new || echo existing)" >> "$results"
  return 0
}

results="data/tmp/fine_category_results.tsv"
: > "$results"

echo ">> 2/3 上传细分类文档到飞书"
fail=0
while IFS=$'\t' read -r cat doc_token title xmlpath needs_create; do
  [ -z "$cat" ] && continue
  [ "$cat" = "category" ] && continue  # skip TSV header
  xmlpath="${xmlpath//\\//}"; xmlpath="${xmlpath%$'\r'}"
  upload_one "$cat" "$doc_token" "$title" "$xmlpath" "$needs_create" || fail=1
  sleep 0.4
done < <(sed 's/\r$//' "$PLAN")

echo ">> 3/3 回写结果到 wiki-config.json"
"$PY" scripts/apply_fine_results.py
if [ "$fail" -eq 0 ]; then echo "完成（全部分类上传成功）。"; else echo "完成（存在失败分类，请查看上方 [FAIL]）。"; fi

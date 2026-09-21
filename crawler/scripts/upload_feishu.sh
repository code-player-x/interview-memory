#!/usr/bin/env bash
# upload_feishu.sh（按分类版 · 一个类别一个文档，大分类自动分片上传）
# 流程：
#   1) gen_upload_plan.py 生成每分类汇总 XML + 上传计划 (category_plan.tsv)
#   2) 循环处理每个分类：
#        - 已有文档(node_token)：直接 docs +update overwrite 改写
#        - 缺文档(needs_create=1)：先在 space root 下 wiki +node-create，再改写
#        - 若单分类 XML 字符数 > GATE，则调用 split_cat_xml.py 切分，用
#          overwrite(片0)+append(片1..) 分片上传，规避单次大体量请求的服务端超时
#   3) apply_category_results.py 把 summary_node_token 回写 wiki-config.json
# 容错：单个分类失败仅记录 [FAIL] 并继续，不会因 set -e 整体中断。
set -uo pipefail
BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BASE"
PY="C:/Users/UserName/.workbuddy/binaries/python/versions/3.13.12/python.exe"
SPACE_ID="7662025183418387409"
GATE=150000        # 单次 overwrite 安全上限（字符数），超过则分片
CHUNK=100000       # 分片后每片目标字符数

echo ">> 1/3 生成分类 XML 与上传计划"
"$PY" scripts/gen_upload_plan.py "$@"

PLAN="data/tmp/category_plan.tsv"
if [ ! -s "$PLAN" ]; then echo "没有待上传的分类计划，结束。"; exit 0; fi

# 计算分类的 sanitize 文件名前缀（与 split_cat_xml.py 保持一致）
sanitize_name() {
  "$PY" -c "import sys; sys.path.insert(0,'scripts'); from split_cat_xml import sanitize; print(sanitize(sys.argv[1]))" "$1"
}

upload_one() {
  local cat="$1" doc_token="$2" title="$3" xmlpath="$4" needs_create="$5"
  local obj="$doc_token" san url
  if [ "$needs_create" = "1" ]; then
    echo "[新建] $cat (space=$SPACE_ID)"
    local nodejson="data/tmp/catnode_${cat}.json"
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
      cat "$xmlpath" | lark-cli docs +update --doc "$obj" --command overwrite --content - --as user --format json > "data/tmp/upd_${cat}.log" 2>&1
      if grep -q '"ok": true' "data/tmp/upd_${cat}.log"; then ok=1; break; fi
      echo "  $cat overwrite attempt $a 失败"; sleep 6
    done
    [ $ok -eq 0 ] && { echo "[FAIL] $cat (overwrite)"; return 1; }
  else
    local nparts=$(( (size + CHUNK - 1) / CHUNK ))
    echo "  $cat 较大(${size}字符)，分 ${nparts} 片上传"
    "$PY" scripts/split_cat_xml.py "$cat" "$nparts" >/dev/null
    local i=0
    while [ -f "data/tmp/cat_${san}_part${i}.xml" ]; do
      local cmd="overwrite"; [ "$i" -gt 0 ] && cmd="append"
      local f="data/tmp/cat_${san}_part${i}.xml" lok=0 a
      for a in 1 2 3 4; do
        cat "$f" | lark-cli docs +update --doc "$obj" --command "$cmd" --content - --as user --format json > "data/tmp/upd_${cat}_p${i}.log" 2>&1
        if grep -q '"ok": true' "data/tmp/upd_${cat}_p${i}.log"; then lok=1; break; fi
        echo "  $cat 片${i}($cmd) attempt $a 失败"; sleep 6
      done
      [ $lok -eq 0 ] && { echo "[FAIL] $cat 片${i}"; return 1; }
      i=$((i+1))
    done
  fi
  url="https://my.feishu.cn/wiki/$obj"
  echo "[OK] $cat -> $url"
  printf '%s\t%s\t%s\t%s\n' "$cat" "$obj" "$url" "$([ "$needs_create" = "1" ] && echo new || echo existing)" >> "$results"
  return 0
}

results="data/tmp/category_results.tsv"
: > "$results"
echo ">> 2/3 循环改写/新建分类文档到飞书"
fail=0
while IFS=$'\t' read -r cat doc_token title xmlpath needs_create; do
  [ -z "$cat" ] && continue
  xmlpath="${xmlpath//\//}"; xmlpath="${xmlpath%$'\r'}"
  upload_one "$cat" "$doc_token" "$title" "$xmlpath" "$needs_create" || fail=1
  sleep 0.4
done < <(sed 's/\r$//' "$PLAN")

echo ">> 3/3 回写分类 summary token 到 wiki-config.json"
"$PY" scripts/apply_category_results.py
if [ "$fail" -eq 0 ]; then echo "完成（全部分类上传成功）。"; else echo "完成（存在失败分类，请查看上方 [FAIL]）。"; fi

"""Walk each Nowcoder search to its reported last page, checkpointing each response."""
import argparse
import hashlib
import json
import time
from datetime import date
from pathlib import Path

import httpx
from harvest_output import output_lock
from nowcoder_harvest import extract_post


def rows(path):
    if path.exists():
        yield from (json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip())


def append(path, row):
    with path.open('a', encoding='utf-8') as stream:
        print(json.dumps(row, ensure_ascii=False), file=stream)


def scan(out, queries, start, end):
    start = date.fromisoformat(start).isoformat()
    end = date.fromisoformat(end).isoformat()
    if start > end:
        raise ValueError("开始日期须早于或等于结束日期")
    out.mkdir(parents=True, exist_ok=True)
    with output_lock(out / 'page-log.jsonl'):
        window = {"date_from": start, "date_to": end}
        metadata = out / 'scan-window.json'
        if metadata.exists():
            if json.loads(metadata.read_text(encoding="utf-8")) != window:
                raise ValueError("此输出目录的日期窗口不同，请为本次扫描指定新的 --out 目录")
        else:
            if any((out / name).exists() for name in ("page-log.jsonl", "candidates.jsonl")):
                raise ValueError("旧扫描未记录日期窗口，请保留旧结果并指定新的 --out 目录")
            temporary = metadata.with_suffix(".tmp")
            temporary.write_text(json.dumps(window), encoding="utf-8")
            temporary.replace(metadata)
        return scan_pages(out, queries, start, end)


def scan_pages(out, queries, start, end):
    log = out / 'page-log.jsonl'
    candidates = out / 'candidates.jsonl'
    history = list(rows(log))
    known = {r['url'] for r in rows(candidates)}
    endpoint = 'https://gw-c.nowcoder.com/api/sparta/pc/search'
    with httpx.Client(timeout=20, headers={'Referer': 'https://www.nowcoder.com/'}) as client:
        # Round robin makes progress on new aliases as well as deep pages on retries.
        unfinished = True
        while unfinished:
            unfinished = False
            for query in queries:
                previous = [r for r in history if r['query'] == query]
                if previous and previous[-1].get('stop'):
                    continue
                unfinished = True
                page = len(previous) + 1
                resp = client.post(endpoint, json={'query':query, 'tab':'post','pageSize':20,'page':page})
                resp.raise_for_status()
                doc = resp.json()
                if not doc.get('success'):
                    raise RuntimeError(f'{query} page {page}: {doc.get("msg")}')
                data = doc['data']; records = data.get('records') or []
                keys = sorted(str(r.get('entityDataId') or r.get('entityId')) for r in records)
                fingerprint = hashlib.sha256(json.dumps(keys).encode()).hexdigest()
                added = 0
                for rec in records:
                    if not isinstance(rec.get('data'), dict):
                        continue
                    post = extract_post(rec,query)
                    if not post or not start <= post['date'] <= end or post['url'] in known:
                        continue
                    append(candidates, post); known.add(post['url']); added += 1
                stop = None
                if not records: stop = 'empty page'
                elif any(p['fingerprint']==fingerprint for p in previous): stop = 'repeated result page'
                elif data.get('totalPage') and page >= data['totalPage']: stop = 'API last page'
                event = dict(query=query,page=page,records=len(records),reported_total=data['total'],reported_pages=data['totalPage'],added=added,fingerprint=fingerprint,stop=stop)
                append(log,event);history.append(event)
                time.sleep(.35)
    return history


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--config',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();conf=json.loads(args.config.read_text(encoding='utf-8'))
    history=scan(args.out,conf['queries'],conf['date_from'],conf['date_to']);print(f'Finished {len(history)} pages')

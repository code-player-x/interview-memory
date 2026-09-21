"""去重驱动：把「(id, text) 记录流」喂给某个策略，产出保留集与重复报告。

与具体策略解耦——无论 rule / semantic / composite，都走同一套循环：
  index(基线) -> 逐条 check -> 重复则记入 dups，否则保留并 add 到索引。
"""


class DedupRunner:
    def __init__(self, strategy, baseline=None):
        self.strategy = strategy
        self.strategy.index(list(baseline or []))
        self.kept = []   # list of (id, text)
        self.dups = []   # list of {id,text,matched,score,detail}

    def process(self, records):
        """records: list of (id, text)。返回 (kept[(id,text)], dups[dict])。"""
        for rid, text in records:
            res = self.strategy.check(text)
            if res.is_duplicate:
                self.dups.append({
                    "id": rid, "text": text,
                    "matched": res.matched,
                    "score": round(res.score, 4),
                    "detail": res.detail,
                })
            else:
                self.kept.append((rid, text))
                self.strategy.add(text)
        return self.kept, self.dups

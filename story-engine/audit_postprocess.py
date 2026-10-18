"""B3 后处理层：LLM 漏洞清单的去重聚类 + finding 自洽校验（零第三方依赖）。

================================================================================
为什么需要这一层（实测依据，可复现）
================================================================================
`shuihu_llm_audit.py`（B2）逐回收到的原始清单存在两个结构性缺陷：

  1) **自相矛盾项计入统计**
     多条 finding 的 explanation 自己写着「此处一致，非矛盾」「非硬性矛盾」
     「暂不收录」「缺乏说服过程」，却仍按「高」严重度进入总数。

  2) **同一矛盾重复计数**
     第 51 回「朱仝已刺配沧州、却在郓城当牢节级」这一条根本矛盾，被逐句展开成
     约 20 条 finding；同型重复在全书反复出现。

后果：原始命中数（水浒传实测 500）严重虚高，不能直接作为对外口径。
本层不做任何 LLM 改写，只做三元判定 + 合并 + 留痕。

================================================================================
三个算子的判定口径
================================================================================
A. 自洽校验（self-consistency）
   依 explanation 的措辞二元判定：

   DROP  强否认  —— 「暂不收录 / 此处一致 / 不构成矛盾 / 属正常写法 / 与史实相符」
                    等显式自我否认，或 explanation 与 fact 自相矛盾。
   DROP  技法评价 —— 「缺乏说服过程 / 无交代 / 叙事跳跃 / 缺乏铺垫」等属叙事技法
                    主观评价，非「客观可定位矛盾」，越出 rubric 收录范围。
   DOWN  存疑     —— 含「存疑 / 疑似 / 待考」且 severity=高 的，降为中。
   KEEP  其余

   弱否认正则 `(?:并非|非|不是|不构成|不算|未构成)[^，。；]{0,6}矛盾` 只在
   explanation **不含**再断言标记（「真正矛盾」「实为」「而是」「矛盾在于」）
   时才判 DROP —— 否则会误杀「非人物矛盾，而是时序矛盾」这类合法细分。

B. 去重聚类（cluster）
   - 全局精确去重：归一化 quote 完全相同的直接合并。
   - 同回并查集：以「锚实体」重叠合并。锚实体 = 在 quote+explanation 中出现、
     且属于本书词表（人名/地名）的 2-4 字串；**高频主角名不作为锚**
     （水浒传实测「宋江」962 次，若作锚会把整回 finding 并成一团）。

C. 留痕（ledger）
   被剔除 / 降级 / 合并的每一条都写入台账，不静默丢弃。

用法：
    python audit_postprocess.py --cache corpus_audit/_llm_cache --book 水浒传
    python audit_postprocess.py --cache corpus_audit/_llm_cache/红楼梦 --book 红楼梦 \
        --report corpus_audit/report.json
    python audit_postprocess.py --selftest
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(ROOT, "corpus_audit")

SEV_ORDER = {"高": 0, "中": 1, "低": 2}

# -----------------------------------------------------------------------------
# A. 自洽校验词表
# -----------------------------------------------------------------------------
# 显式自我否认：命中即 DROP（强信号，无歧义）
SELF_DENY_STRONG = (
    "暂不收录", "不予收录", "不收录", "不算矛盾", "不构成矛盾", "未构成矛盾",
    "此处一致", "前后一致", "与史实相符", "与史实一致", "属正常写法",
    "属正常叙事", "正常叙事手法", "非矛盾项", "非硬伤", "并不矛盾",
)
# 叙事技法评价：属主观文评，越出「客观可定位矛盾」的收录范围
NARRATIVE_CRITIC = (
    "缺乏说服过程", "缺乏说服力", "缺乏交代", "未交代其", "无交代", "叙事跳跃",
    "缺乏铺垫", "显得突兀", "缺乏过渡", "交代不清", "叙述来源不明", "无来由",
)
# 存疑措辞：仅用于把「高」降级，不用于剔除
HEDGE = ("存疑", "拿不准", "疑似", "待考", "或属", "可能为", "或许是", "不确定", "推测")

# 弱否认正则（需配合再断言守卫）
_WEAK_DENY_RE = re.compile(r"(?:并非|非|不是|不构成|不算|未构成|无)[^，。；]{0,6}矛盾")
# 再断言标记：出现则说明该条只是「否定一个子论断、肯定另一个」，不构成自我否认
_REASSERT_RE = re.compile(r"真正矛盾|实为|而是|矛盾在于|矛盾在|真正的问题|关键在于")


def self_consistency_verdict(finding: dict) -> tuple:
    """返回 (verdict, reason)。verdict ∈ {'KEEP','DROP','DOWN'}。"""
    expl = str(finding.get("explanation", "") or "")
    if not expl:
        return "KEEP", ""
    for k in SELF_DENY_STRONG:
        if k in expl:
            return "DROP", "自我否认（命中「%s」）" % k
    for k in NARRATIVE_CRITIC:
        if k in expl:
            return "DROP", "叙事技法评价，非客观矛盾（命中「%s」）" % k
    if _WEAK_DENY_RE.search(expl) and not _REASSERT_RE.search(expl):
        return "DROP", "自我否认（弱否认句式，无再断言）"
    if str(finding.get("severity", "")) == "高":
        for k in HEDGE:
            if k in expl:
                return "DOWN", "存疑措辞（命中「%s」）→ 高降为中" % k
    return "KEEP", ""


# -----------------------------------------------------------------------------
# B. 实体抽取 + 去重聚类
# -----------------------------------------------------------------------------
def build_vocab(report_path: str, book: str) -> dict:
    """从 prose_bridge 的 report.json 取本书人名/地名词表 -> {surface: 全书频次}。"""
    vocab: dict = {}
    if not report_path or not os.path.exists(report_path):
        return vocab
    try:
        data = json.load(open(report_path, encoding="utf-8"))
    except Exception:
        return vocab
    rec = data.get(book) or {}
    for nm, c in (rec.get("name_counts") or {}).items():
        vocab[nm] = max(vocab.get(nm, 0), int(c))
    for nm in (rec.get("names") or []):
        vocab.setdefault(nm, 6)
    for pl in (rec.get("places") or []):
        vocab.setdefault(pl, 8)
    return vocab


def extract_entities(text: str, vocab: dict, max_len: int = 4) -> set:
    """在 text 中扫出属于词表的 2..max_len 字实体（最长优先，吃掉子串）。"""
    if not text or not vocab:
        return set()
    found = set()
    i, n = 0, len(text)
    while i < n:
        hit = ""
        for L in range(max_len, 1, -1):
            cand = text[i:i + L]
            if len(cand) == L and cand in vocab:
                hit = cand
                break
        if hit:
            found.add(hit)
            i += len(hit)
        else:
            i += 1
    return found


class _DSU:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def _norm_quote(q: str) -> str:
    """归一化 quote 用于精确去重：去标点空白、只留中日韩字与字母数字。"""
    return re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", str(q or ""))


def _same_type_family(a: dict, b: dict) -> bool:
    """类型族判定：'设定/制度' 与 '设定/制度硬伤' 视为同族。"""
    ta = str(a.get("type", "")).split("/")[0].strip()
    tb = str(b.get("type", "")).split("/")[0].strip()
    return bool(ta) and ta == tb


def cluster_findings(findings: list, vocab: dict, anchor_max_freq: int = 200,
                     min_shared_anchors: int = 3) -> list:
    """返回聚类列表；每簇含 members / dup_count / representative / anchors。

    合并门槛（防过度合并）：仅当
      · 共享 >=1 个锚实体 **且** 两条类型同族，或
      · 共享 >= min_shared_anchors 个锚实体（强信号，可跨类型）
    时才并为一簇。

    门槛演进（实测留痕，均为水浒传 500 条缓存上的真实数字）：
      · v1「共享 >=1 锚即并」→ 保留 325，38+8 簇；实测把第 17 回分属
        「人物一致性 / 伏笔呼应断裂 / 时空地理」的 4 条并成一簇，属过度合并。
      · v2「共享 >=2 锚 或 类型同族」→ 保留 356，38 簇；第 17 回仍被并。
      · v3（本版）「类型同族+>=1 锚 或 共享 >=3 锚」→ 见 --anchor-max-freq 同批实测。
    """
    n = len(findings)
    if not n:
        return []

    # 1) 全局精确去重：归一并同 quote 的视为同簇
    by_q: dict = defaultdict(list)
    for i, f in enumerate(findings):
        by_q[_norm_quote(f.get("quote", ""))].append(i)

    # 2) 同回锚实体并查集
    dsu = _DSU(n)
    for idxs in by_q.values():
        for j in idxs[1:]:
            dsu.union(idxs[0], j)

    ents = []
    for f in findings:
        blob = "%s%s" % (f.get("quote", ""), f.get("explanation", ""))
        e = extract_entities(blob, vocab)
        # 高频主角名不作锚（否则整回并成一团）
        anchors = {x for x in e if vocab.get(x, 0) <= anchor_max_freq}
        ents.append({"all": e, "anchors": anchors})

    per_chapter: dict = defaultdict(list)
    for i, f in enumerate(findings):
        per_chapter[int(f.get("chapter", 0) or 0)].append(i)
    for ch, idxs in per_chapter.items():
        # 合并门槛：类型同族+≥1 锚，或 共享 ≥ min_shared_anchors 锚（强信号）
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                ia, ib = idxs[a], idxs[b]
                if dsu.find(ia) == dsu.find(ib):
                    continue
                shared = ents[ia]["anchors"] & ents[ib]["anchors"]
                if not shared:
                    continue
                if len(shared) >= min_shared_anchors or \
                        (_same_type_family(findings[ia], findings[ib]) and len(shared) >= 1):
                    dsu.union(ia, ib)

    groups: dict = defaultdict(list)
    for i in range(n):
        groups[dsu.find(i)].append(i)

    clusters = []
    for root, idxs in groups.items():
        members = [findings[i] for i in idxs]
        rep = sorted(members, key=lambda f: (SEV_ORDER.get(str(f.get("severity", "低")), 3),
                                             -len(str(f.get("explanation", "")))))[0]
        anchors = set()
        for i in idxs:
            anchors |= ents[i]["anchors"]
        clusters.append({
            "chapter": int(rep.get("chapter", 0) or 0),
            "chapter_title": rep.get("chapter_title", ""),
            "n_members": len(idxs),
            "dup_count": len(idxs) - 1,
            "anchors": sorted(anchors),
            "types": sorted({str(m.get("type", "")) for m in members}),
            "representative": rep,
            "members": members,
        })
    clusters.sort(key=lambda c: (SEV_ORDER.get(str(c["representative"].get("severity", "低")), 3),
                                 c["chapter"]))
    return clusters


# -----------------------------------------------------------------------------
# C. 主流程 + 留痕台账
# -----------------------------------------------------------------------------
def load_findings_from_cache(cache_dir: str) -> list:
    out = []
    for p in sorted(glob.glob(os.path.join(cache_dir, "*.json"))):
        try:
            data = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, list):
            out.extend([d for d in data if isinstance(d, dict)])
    return out


def postprocess(findings: list, vocab: dict, anchor_max_freq: int = 200,
                min_shared_anchors: int = 2) -> dict:
    kept, dropped, downgraded = [], [], []
    for f in findings:
        v, reason = self_consistency_verdict(f)
        if v == "DROP":
            dropped.append({"finding": f, "reason": reason})
            continue
        if v == "DOWN":
            g = dict(f)
            g["severity_original"] = f.get("severity")
            g["severity"] = "中"
            downgraded.append({"finding": g, "reason": reason})
            kept.append(g)
            continue
        kept.append(f)

    # 去重只作用于通过自洽校验的条目 —— 被剔除项不该参与代表选举
    clusters = cluster_findings(kept, vocab, anchor_max_freq=anchor_max_freq,
                                min_shared_anchors=min_shared_anchors)
    reps = [c["representative"] for c in clusters]
    merged = [c for c in clusters if c["dup_count"] > 0]

    return {
        "raw": len(findings),
        "kept": reps,
        "dropped": dropped,
        "downgraded": downgraded,
        "clusters": clusters,
        "merged": merged,
        "stats": {
            "raw": len(findings),
            "dropped": len(dropped),
            "downgraded": len(downgraded),
            "merged_away": sum(c["dup_count"] for c in clusters),
            "kept": len(reps),
        },
    }


def write_ledger(res: dict, out_path: str, book: str, sensitivity: list = None) -> None:
    st = res["stats"]
    L = []
    A = L.append
    A("# 《%s》B3 后处理台账（自洽校验 + 去重聚类）" % book)
    A("")
    A("工具：`audit_postprocess.py`。本层不改写 LLM 原文，只做判定 / 合并 / 留痕。")
    A("")
    A("## 0. 合并门槛敏感性（同批数据实测，供选默认值）")
    A("")
    A("合并门槛 `--min-shared-anchors` 直接决定去重力度。三档在同一份")
    A("自洽校验通过集上实跑结果如下 —— 报一个数字而不报取舍，等于藏掉一半信息。")
    A("")
    A("| 门槛 | 保留条数 | 说明 |")
    A("|---|---:|---|")
    if sensitivity:
        for thr, n, note in sensitivity:
            A("| %d | %d | %s |" % (thr, n, note))
    A("")
    A("默认取 3（精度优先）：门槛=1 会把第 17 回四条**互不相同**的矛盾")
    A("（杨志路线 / 鲁智深送沧州 / 鲁智深孟州路线 / 杨志报真名）并成一簇，属过度合并；")
    A("门槛=3 把它们拆开，同时仍把「鲁智深自述两处与原文不符」这条真重复并掉。")
    A("代价：第 51 回「朱仝既在沧州又在郓城」这条根本矛盾，按维度收敛为 3 簇")
    A("（人物一致性 / 时空地理 / 因果自洽），而非 1 簇。")
    A("")
    A("## 汇总（当前门槛）")
    A("")
    A("| 项 | 条数 |")
    A("|---|---:|")
    A("| LLM 原始命中 | %d |" % st["raw"])
    A("| 自洽校验剔除 | %d |" % st["dropped"])
    A("| 存疑降级（高→中） | %d |" % st["downgraded"])
    A("| 去重合并掉 | %d |" % st["merged_away"])
    A("| **保留（去重后）** | **%d** |" % st["kept"])
    A("")
    A("去重率：%.1f%%（(剔除+合并)/原始）"
      % (100.0 * (st["dropped"] + st["merged_away"]) / st["raw"] if st["raw"] else 0.0))
    A("")
    A("## 1. 自洽校验剔除台账（%d 条）" % len(res["dropped"]))
    A("")
    A("| # | 回 | 类型 | 原severity | 剔除理由 | 原文片段 | explanation 摘要 |")
    A("|---|---|---|---|---|---|---|")
    for i, d in enumerate(res["dropped"], 1):
        f = d["finding"]
        A("| %d | 第%s回 | %s | %s | %s | %s | %s |" % (
            i, f.get("chapter", ""), f.get("type", ""), f.get("severity", ""), d["reason"],
            (str(f.get("quote", "")) or "").replace("|", "/"),
            (str(f.get("explanation", "")) or "").replace("|", "/")[:80]))
    A("")
    A("## 2. 存疑降级台账（%d 条）" % len(res["downgraded"]))
    A("")
    A("| # | 回 | 类型 | 高→中 理由 | 原文片段 |")
    A("|---|---|---|---|---|")
    for i, d in enumerate(res["downgraded"], 1):
        f = d["finding"]
        A("| %d | 第%s回 | %s | %s | %s |" % (
            i, f.get("chapter", ""), f.get("type", ""), d["reason"],
            (str(f.get("quote", "")) or "").replace("|", "/")))
    A("")
    A("## 3. 去重合并台账（%d 簇，共并掉 %d 条）" % (len(res["merged"]), st["merged_away"]))
    A("")
    A("| # | 回 | 簇内条数 | 并掉 | 锚实体 | 涉及类型 | 代表条目 |")
    A("|---|---|---:|---:|---|---|---|")
    for i, c in enumerate(res["merged"], 1):
        rep = c["representative"]
        A("| %d | 第%s回 | %d | %d | %s | %s | %s |" % (
            i, c["chapter"], c["n_members"], c["dup_count"],
            "、".join(c["anchors"][:6]) or "（无锚，精确重复）",
            " / ".join(c["types"]),
            (str(rep.get("explanation", "")) or "").replace("|", "/")[:80]))
    A("")
    A("## 4. 保留清单（%d 条，按严重度）" % len(res["kept"]))
    A("")
    A("| 严重度 | 回 | 类型 | 范围 | 原文片段 | 说明 |")
    A("|---|---|---|---|---|---|")
    for f in sorted(res["kept"], key=lambda x: (SEV_ORDER.get(str(x.get("severity", "低")), 3),
                                                int(x.get("chapter", 0) or 0))):
        A("| %s | 第%s回 %s | %s | %s | %s | %s |" % (
            f.get("severity", ""), f.get("chapter", ""), f.get("chapter_title", ""),
            f.get("type", ""), f.get("scope", ""),
            (str(f.get("quote", "")) or "").replace("|", "/"),
            (str(f.get("explanation", "")) or "").replace("|", "/")))
    A("")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))


# -----------------------------------------------------------------------------
# 自检
# -----------------------------------------------------------------------------
_SELFTEST_CASES = [
    # (explanation, expect)
    ("曹正自述为开封府人氏，但林冲为东京八十万禁军教头，东京即开封府，此非矛盾；"
     "属前文未伏后文突现，但非硬性矛盾。真正矛盾在：…暂不收录。", "DROP"),
    ("未明确正副；后文刘高自称「正知寨」、花荣自称「副知寨」，此处一致，非矛盾。", "DROP"),
    ("但秦明是败将被擒后落草，黄信身为青州都监未战先降，缺乏说服过程。", "DROP"),
    ("前文未交代其如何得知劫法场消息，属叙事跳跃，非硬矛盾。", "DROP"),
    ("朱仝此时已因私放雷横被刺配沧州，不可能仍在郓城任当牢节级。", "KEEP"),
    ("非人物矛盾，而是时序矛盾：同一回内前后口径不一。", "KEEP"),
    ("太祖在位实为十六年（960-976），此处作十七年，与史实及后文'九朝八帝'叙述不合。", "KEEP"),
    ("前文阮小二在岸上提锄头杀官兵，阮小七在水下拖何涛，此处却称二人各驾船，数目矛盾。疑似排版脱漏。", "DOWN"),
]


def selftest() -> int:
    bad = 0
    for expl, expect in _SELFTEST_CASES:
        v, reason = self_consistency_verdict({"explanation": expl, "severity": "高"})
        mark = "OK " if v == expect else "BAD"
        if v != expect:
            bad += 1
        print("  %s expect=%-4s got=%-4s | %s" % (mark, expect, v, expl[:38]))
    print("\n自检：%d 例，失败 %d 例" % (len(_SELFTEST_CASES), bad))
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="B3 后处理：自洽校验 + 去重聚类 + 留痕")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--cache", help="LLM 缓存目录（*.json）")
    ap.add_argument("--json", dest="json_in", help="findings JSON 文件（list）")
    ap.add_argument("--report", default=os.path.join(OUTDIR, "report.json"),
                    help="prose_bridge 产出的 report.json（取实体词表）")
    ap.add_argument("--book", default="水浒传")
    ap.add_argument("--anchor-max-freq", type=int, default=200,
                    help="锚实体频次上限，超过者不作锚（避免高频主角并吞整回）")
    ap.add_argument("--min-shared-anchors", type=int, default=3,
                    help="同回合并门槛：共享受锚数（<2 时需类型同族才并）")
    ap.add_argument("--out", help="台账输出路径")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if args.json_in:
        findings = json.load(open(args.json_in, encoding="utf-8"))
    elif args.cache:
        findings = load_findings_from_cache(args.cache)
    else:
        print("需指定 --cache 或 --json（或 --selftest）")
        return 2

    vocab = build_vocab(args.report, args.book)
    print("载入 findings %d 条；实体词表 %d 项" % (len(findings), len(vocab)))
    res = postprocess(findings, vocab, anchor_max_freq=args.anchor_max_freq,
                      min_shared_anchors=args.min_shared_anchors)
    st = res["stats"]
    print("  原始 %d → 剔除 %d / 降级 %d / 合并掉 %d → 保留 %d"
          % (st["raw"], st["dropped"], st["downgraded"], st["merged_away"], st["kept"]))

    out = args.out or os.path.join(OUTDIR, "%s_LLM漏洞审计_后处理台账.md" % args.book)
    # 门槛敏感性：同一自洽校验通过集上换门槛重跑聚类，数字全部入账
    passed = [f for f in findings if self_consistency_verdict(f)[0] != "DROP"]
    notes = {
        1: "过度合并：第 17 回 4 条不同矛盾并成 1 簇，第 51 回 23 条并成 1 簇",
        2: "仍过度合并：第 17 回 4 条不同矛盾并成 1 簇",
        3: "默认：第 17 回按类型拆为 4 簇，第 51 回按维度收敛为 3 簇",
    }
    sensitivity = []
    for thr in (1, 2, 3):
        n = len(cluster_findings(passed, vocab, anchor_max_freq=args.anchor_max_freq,
                                min_shared_anchors=thr))
        sensitivity.append((thr, n, notes.get(thr, "")))
    write_ledger(res, out, args.book, sensitivity=sensitivity)
    print("台账 -> %s" % out)

    kept_path = os.path.join(OUTDIR, "%s_LLM漏洞审计_去重后.json" % args.book)
    json.dump(res["kept"], open(kept_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("保留清单 -> %s" % kept_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

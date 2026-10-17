# -*- coding: utf-8 -*-
"""红楼梦 × Story Engine for Creator：全书审计运行器（决定论、零外部依赖）。

用法：
    python hlm_audit.py                     # 审计全部 120 回
    python hlm_audit.py --chapters 1-80     # 只审计第 1-80 回
    python hlm_audit.py --chapters 81-120   # 只审计第 81-120 回（续书）
    python hlm_audit.py --split             # 前 80 / 后 40 分体对照报告

产出（corpus_audit/ 下）：
    红楼梦_引擎审计.json     逐回结构化指标 + 哈希链
    红楼梦_引擎审计报告.md   分体对照报告（前80 vs 后40）

设计约束：
    - 只调用引擎公开入口 audit_text / audit_prose，不改引擎语义；
    - 叙事立场固定 omniscient（红楼梦是说书人全知视角，chronicler 会把
      「原来」「殊不知」误判为全知解说腔）；
    - 角色词表 + 别称档案随附，用于说话人归属与近距复用人名豁免。
"""
import argparse
import importlib.util
import json
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_PATH = os.path.join(HERE, "Story Engine for Creator.py")
CORPUS = os.path.join(HERE, "corpus", "红楼梦")
OUTDIR = os.path.join(HERE, "corpus_audit")

# ——— 红楼梦人物词表（本名 + 别称；用于严格词表模式与人名豁免）———
NAMES = [
    "賈寶玉", "寶玉", "寶二爺", "怡紅公子", "絳洞花主",
    "林黛玉", "黛玉", "林姑娘", "顰兒", "瀟湘妃子", "顰顰",
    "薛寶釵", "寶釵", "寶姐姐", "蘅蕪君", "寶丫頭",
    "王熙鳳", "鳳姐", "鳳丫頭", "琏二奶奶", "鳳辣子", "熙鳳",
    "賈母", "老太太", "史太君", "太夫人",
    "史湘雲", "湘雲", "雲姑娘", "枕霞舊友",
    "賈探春", "探春", "蕉下客", "玫瑰花",
    "賈迎春", "迎春", "二木頭", "二姑娘",
    "賈惜春", "惜春", "四姑娘",
    "李紈", "紈兒", "大奶奶", "稻香老農",
    "王夫人", "太太", "二太太",
    "邢夫人", "大太太", "邢氏",
    "薛姨媽", "姨媽", "薛王氏",
    "賈政", "政老爺", "二老爺",
    "賈赦", "赦老爺", "大老爺",
    "賈璉", "璉二爺", "璉哥兒",
    "賈珍", "珍大爺", "尤氏", "大奶奶",
    "秦可卿", "可卿", "秦氏", "蓉大奶奶",
    "賈蓉", "蓉哥兒", "賈薔", "薔哥兒",
    "妙玉", "檻外人", "檻內人",
    "平兒", "平姑娘", "鴛鴦", "鴛鴦姐",
    "襲人", "襲人姐", "花大姐姐", "珍珠",
    "晴雯", "晴雯姐", "勇晴雯", "黛丫頭",
    "紫鵑", "紫鵑姐", "雪雁", "鸚哥",
    "金釧", "金釧兒", "玉釧", "玉釧兒",
    "香菱", "甄英蓮", "英蓮", "秋菱",
    "秋紋", "秋紋姐", "碧痕", "碧月", "綺霰", "小紅", "紅玉", "林紅玉",
    "司棋", "司棋姐", "待書", "入畫", "彩屏", "彩雲", "彩霞", "素雲",
    "焙茗", "茗煙", "李貴", "王榮", "錢華", "周瑞", "周瑞家的", "眾人", "眾人聽了",
    "賈環", "環三爺", "趙姨娘", "趙姨奶奶", "周姨娘", "周姨奶奶",
    "賈蘭", "蘭哥兒", "賈菌", "賈芸", "芸二爺", "賈芹", "賈璿",
    "秦鐘", "秦鯨卿", "蔣玉菡", "琪官", "柳湘蓮", "湘蓮", "柳二哥",
    "北靜王", "水溶", "南安郡王", "東平郡王", "西寧郡王",
    "賈雨村", "雨村", "賈化", "時飛", "賈寶玉之父",
    "甄士隱", "士隱", "甄費", "封肅", "封氏", "嬌杏", "英蓮",
    "劉姥姥", "劉氏", "板兒", "青兒", "巧姐兒", "巧姐", "大姐兒",
    "林如海", "如海", "賈敏", "敏", "賈代化", "賈代善", "賈代儒",
    "賈瑞", "瑞大爺", "賈天祥", "尤二姐", "尤三姐", "尤老娘",
    "張如圭", "冷子興", "子興", "賈赦之", "智能", "智能兒",
    "馬道婆", "趙嬤嬤", "周善保家的", "王善保家的", "林之孝",
    "林之孝家的", "王熙鳳之", "旺兒", "旺兒媳婦", "來旺家的",
    "焦大", "賴大", "賴二", "俞祿", "丫環", "小廝",
]

# ——— 别名档案（canonical → aliases）：说话人归属 / 认知 / 语域审计用 ———
PROFILES = {
    "賈寶玉": {"aliases": ["寶玉", "寶二爺", "怡紅公子", "絳洞花主"]},
    "林黛玉": {"aliases": ["黛玉", "林姑娘", "顰兒", "瀟湘妃子", "顰顰"]},
    "薛寶釵": {"aliases": ["寶釵", "寶姐姐", "蘅蕪君", "寶丫頭"]},
    "王熙鳳": {"aliases": ["鳳姐", "鳳丫頭", "琏二奶奶", "鳳辣子", "熙鳳"]},
    "賈母": {"aliases": ["老太太", "史太君", "太夫人"]},
    "史湘雲": {"aliases": ["湘雲", "雲姑娘", "枕霞舊友"]},
    "賈探春": {"aliases": ["探春", "蕉下客", "玫瑰花"]},
    "秦可卿": {"aliases": ["可卿", "秦氏", "蓉大奶奶"]},
    "賈雨村": {"aliases": ["雨村", "賈化", "時飛"]},
    "甄士隱": {"aliases": ["士隱", "甄費"]},
    "劉姥姥": {"aliases": ["劉氏"]},
    "妙玉": {"aliases": ["檻外人", "檻內人"]},
    "香菱": {"aliases": ["甄英蓮", "英蓮", "秋菱"]},
    "襲人": {"aliases": ["襲人姐", "花大姐姐", "珍珠"]},
    "晴雯": {"aliases": ["晴雯姐", "勇晴雯"]},
    "小紅": {"aliases": ["紅玉", "林紅玉"]},
}


def load_engine():
    spec = importlib.util.spec_from_file_location("story_engine_creator", ENGINE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    conflicts = mod.check_engine_isolation()
    if conflicts:
        print("[FATAL] 引擎隔离冲突：", conflicts)
        sys.exit(2)
    return mod


def chapter_files(selection: str):
    files = sorted(f for f in os.listdir(CORPUS) if f.endswith(".txt"))
    if selection == "all":
        return files
    lo, hi = (int(x) for x in selection.split("-"))
    return [f for f in files if lo <= int(f[:3]) <= hi]


def audit_chapter(engine, mod, path):
    text = open(path, encoding="utf-8").read()
    rep = engine.audit_text(
        text=text,
        narration_mode="omniscient",   # 说书人全知视角
        include_causal=True,
        characters=PROFILES,
        known_names=NAMES,
    )
    ps = rep["presentation"]["prose_style"]
    pres = rep["presentation"]
    causal = rep["causal"] or {}
    chain = causal.get("chain") or []
    dialogues = mod._extract_dialogues(text)
    return {
        "chapter": os.path.basename(path)[:3],
        "title": os.path.basename(path)[4:-4],
        "chars": len(text),
        "sentences": len(ps and mod.ProseStyleAuditor._split_sentences(text)),
        "style_family": ps.get("style_family"),
        "narration_mode": pres.get("narration_mode"),
        # —— 文风指标（分体对照的主特征）——
        "avg_sentence_len": round(
            mod.ProseStyleAuditor._han_chars(text)
            / max(1, len(mod.ProseStyleAuditor._split_sentences(text))), 2),
        "virtual_density": ps["redundancy"]["metric"],
        "rhythm_cv": ps["rhythm_monotone"].get("metric"),
        "tell_density": ps["show_dont_tell"].get("metric"),
        "head_hop": ps["pov_head_hop"].get("hop_density_per100"),
        "lexical_repeat_hits": len(ps["lexical_repeat"].get("hits", [])),
        "lexical_repeat_frags": [h["fragment"] for h in ps["lexical_repeat"].get("hits", [])],
        "redundant_pairs": ps["redundancy"].get("redundant_pairs", []),
        "register_drift_hits": len(ps["register_drift"].get("hits", [])),
        "dialogue_count": len(dialogues),
        "dialogue_density": round(len(dialogues) / max(1, len(text)) * 1000, 3),
        "narration_issues": len(pres["narration_perspective"].get("issues", [])),
        "era_issues": len(pres["dialogue_era"].get("issues", [])),
        "cognition_issues": len(pres["dialogue_cognition"].get("issues", [])),
        "registry_issues": len(pres["dialogue_registry"].get("issues", [])),
        "prose_passed": ps.get("passed"),
        "prose_failed": ps.get("failed_detectors", []),
        # —— 因果层 ———
        "causal_events": len(chain),
        "causal_dangling": sum(1 for e in chain if e.get("dangling")),
        "causal_collapse": causal.get("collapse_verdict"),
        "causal_converged": (causal.get("reconstruction") or {}).get("converged"),
        # —— 台账 / 时空 / 存证 ———
        "foreshadow_set": rep["foreshadow"]["ledger"]["set_count"],
        "foreshadow_pay": rep["foreshadow"]["ledger"]["pay_count"],
        "spacetime_checked": (rep.get("spacetime") or {}).get("checked_nodes", 0),
        "all_passed": rep["all_passed"],
        "audit_hash": rep.get("audit_hash"),
        "audit_prev_hash": rep.get("audit_prev_hash"),
    }


def summarize(rows):
    keys = ["avg_sentence_len", "virtual_density", "rhythm_cv", "tell_density",
            "head_hop", "lexical_repeat_hits", "dialogue_density",
            "causal_dangling", "causal_events"]
    out = {}
    for k in keys:
        xs = [r[k] for r in rows if isinstance(r.get(k), (int, float))]
        if not xs:
            out[k] = None
            continue
        out[k] = {
            "n": len(xs), "mean": round(statistics.mean(xs), 4),
            "median": round(statistics.median(xs), 4),
            "stdev": round(statistics.stdev(xs), 4) if len(xs) > 1 else 0.0,
            "min": round(min(xs), 4), "max": round(max(xs), 4),
        }
    out["_chapters"] = len(rows)
    out["_prose_failed_chapters"] = sum(1 for r in rows if not r["prose_passed"])
    out["_causal_collapse"] = {}
    for r in rows:
        v = r.get("causal_collapse")
        out["_causal_collapse"][v] = out["_causal_collapse"].get(v, 0) + 1
    return out


def write_report(rows, front, back, out_md):
    L = []
    A = L.append
    A("# 《红楼梦》Story Engine 审计报告（分体对照）")
    A("")
    A("引擎：`Story Engine for Creator.py`（五层审计 + 哈希链存证）。")
    A("叙事立场：omniscient（说书人全知视角）。角色词表 %d 项，别名档案 %d 组。" % (len(NAMES), len(PROFILES)))
    A("")
    A("## 汇总")
    A("")
    A("| 指标 | 前 80 回（n=%d） | 后 40 回（n=%d） |" % (len(front), len(back)))
    A("|---|---|---|")
    sf = summarize(front)
    sb = summarize(back)
    for k in ("avg_sentence_len", "virtual_density", "rhythm_cv", "tell_density",
              "head_hop", "lexical_repeat_hits", "dialogue_density",
              "causal_dangling", "causal_events"):
        a, b = sf.get(k), sb.get(k)
        if not a or not b:
            continue
        A("| %s | 均值 %.3f / 中位 %.3f / 标准差 %.3f | 均值 %.3f / 中位 %.3f / 标准差 %.3f |"
          % (k, a["mean"], a["median"], a["stdev"], b["mean"], b["median"], b["stdev"]))
    A("| prose_style 未通过回数 | %d | %d |" % (sf["_prose_failed_chapters"], sb["_prose_failed_chapters"]))
    A("")
    A("因果层判决分布：前80 %s；后40 %s" % (json.dumps(sf["_causal_collapse"], ensure_ascii=False),
                                          json.dumps(sb["_causal_collapse"], ensure_ascii=False)))
    A("")
    A("## 哈希链")
    A("")
    A("首块 %s … 末块 %s（共 %d 块，逐回 audit_hash 见 JSON）。"
      % (rows[0]["audit_prev_hash"][:12], rows[-1]["audit_hash"][:12], len(rows)))
    A("")
    A("## 方法与边界")
    A("")
    A("- 本报告只复述引擎输出，不做文学判断；分体差异是量化签名，不是续书作者结论。")
    A("- 台词认知/语域审计依赖角色档案的 forbidden_knowledge / register_hints，"
      "本轮未配置知识模型，故这两项按设计跳过（未产出相关结论）。")
    A("- 伏笔台账为显式关键词对账（埋下/回收），红楼梦正文不用此类元语言，"
      "故 set/pay 计数接近 0 属预期，不代表无伏笔。")
    A("- 时空校验仅对同时声明角色/时间/地点的节点生效，散文路径不声明时空，"
      "checked_nodes=0 属预期。")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapters", default="all", help="如 1-80 / 81-120 / all")
    ap.add_argument("--out-json", default=os.path.join(OUTDIR, "红楼梦_引擎审计.json"))
    ap.add_argument("--out-md", default=os.path.join(OUTDIR, "红楼梦_引擎审计报告.md"))
    args = ap.parse_args()

    mod = load_engine()
    engine = mod.UltimateCausalNovelEngine("红楼梦", mod.GlobalState())
    files = chapter_files(args.chapters)
    rows = []
    for i, path in enumerate(files):
        r = audit_chapter(engine, mod, os.path.join(CORPUS, path))
        rows.append(r)
        if (i + 1) % 20 == 0 or i + 1 == len(files):
            print("  已审计 %d/%d 回" % (i + 1, len(files)))
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    front = [r for r in rows if int(r["chapter"]) <= 80]
    back = [r for r in rows if int(r["chapter"]) > 80]
    if front and back:
        write_report(rows, front, back, args.out_md)
    elif rows:
        s = summarize(rows)
        with open(args.out_md, "w", encoding="utf-8") as f:
            f.write("# 《红楼梦》Story Engine 审计（第 %s 回）\n\n" % args.chapters)
            f.write("```json\n%s\n```\n" % json.dumps(s, ensure_ascii=False, indent=1))
    print("完成：%d 回 → %s" % (len(rows), args.out_json))
    print("报告：%s" % args.out_md)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""detect_logic_gaps：逻辑漏洞自动检测编排器（三段式的第二、三段 + 验收）。

用法：
    python detect_logic_gaps.py --nodes golden_samples.json                 # 审计模式
    python detect_logic_gaps.py --nodes golden_samples.json --accept         # 验收模式（对黄金样本判分）
    python detect_logic_gaps.py --nodes x.json --out-json out.json --out-md out.md

流程：载入 EventNode → 四校验器 → 责任锚定 → 哈希存证 → 报告。
上游抽取（散文 → EventNode）由 extraction/ 提供；本编排器不直接读散文。
"""
import argparse
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_PATH = os.path.join(HERE, "Story Engine for Creator.py")

sys.path.insert(0, HERE)
from extraction.schema import load_nodes, dump_nodes, schema_doc  # noqa: E402
import logic_validators as LV  # noqa: E402


def load_engine():
    spec = importlib.util.spec_from_file_location("story_engine_creator", ENGINE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def anchor(nodes, results):
    """责任锚定：把每条冲突锚到最小决策单元（角色 + 动作 + 原文定位）。"""
    src = {n.character: n.source for n in nodes}
    anchors = []
    for kind in LV.VALIDATORS:
        for c in results.get(kind, {}).get("conflicts", []):
            anchors.append({
                "accountable": c.get("character", ""),
                "decision_unit": c.get("detail", ""),
                "violation_type": c.get("type", kind),
                "evidence": c.get("sources", []),
                "source_lookup": src.get(c.get("character", ""), ""),
            })
    return anchors


def accept(nodes, results):
    """验收：对带 gold 标注的样本判分（召回率 / 误报数）。"""
    groups = {}
    for n in nodes:
        if n.gold:
            gid = n.gold.split("#")[0]
            groups.setdefault(gid, {"chars": set(), "sources": [], "topics": set()})
            groups[gid]["chars"].add(n.character)
            groups[gid]["sources"].append(n.source)
            if n.topic:
                groups[gid]["topics"].add(n.topic)
    hits = {}
    for kind in LV.VALIDATORS:
        for c in results.get(kind, {}).get("conflicts", []):
            hits.setdefault(kind, []).append(c)
    detected = set()
    for gid, g in groups.items():
        for kind, cs in hits.items():
            for c in cs:
                if c.get("character") in g["chars"] or c.get("topic") in g.get("topics", set()):
                    detected.add(gid)
                    break
    unrecovered = set(results.get("foreshadow", {}).get("unrecovered", []))
    for gid, g in groups.items():
        if g["topics"] & unrecovered:
            detected.add(gid)
    total = len(groups)
    return {
        "gold_groups": total,
        "detected_groups": len(detected),
        "recall": round(len(detected) / total, 3) if total else None,
        "missed": sorted(set(groups) - detected),
        "total_conflicts_reported": results.get("total_conflicts", 0),
    }


def write_md(nodes, results, anchors, path, acc=None):
    L = []
    A = L.append
    A("# 逻辑漏洞检测报告")
    A("")
    A("编排器：`detect_logic_gaps.py` ｜ 校验器：`logic_validators.py` ｜ 契约：`extraction/schema.py`")
    A("")
    A("输入节点 %d 条（角色 %d 个）" % (len(nodes), len({n.character for n in nodes})))
    A("")
    A("## 校验结果")
    A("")
    A("| 校验器 | 参与节点 | 通过 | 冲突数 |")
    A("|---|---|---|---|")
    for k in LV.VALIDATORS:
        v = results.get(k, {})
        n_conf = len(v.get("conflicts", []))
        A("| %s | %s | %s | %d |" % (k, v.get("checked", "-"),
                                     "是" if v.get("passed") else "否", n_conf))
    A("")
    conflicts = [(k, c) for k in LV.VALIDATORS for c in results.get(k, {}).get("conflicts", [])]
    if conflicts:
        A("## 漏洞清单（可回原文核验）")
        A("")
        A("| 类型 | 角色 | 详情 | 原文定位 |")
        A("|---|---|---|---|")
        for k, c in conflicts:
            A("| %s | %s | %s | %s |" % (c.get("type", k), c.get("character", ""),
                                        c.get("detail", ""), "；".join(c.get("sources", []))[:60]))
        A("")
    else:
        A("## 漏洞清单")
        A("")
        A("未检出冲突。注意：坐标为空的节点不参与校验（宁缺毋滥），"
          "因此「未检出」不等于「无漏洞」。")
        A("")
    if anchors:
        A("## 责任锚定")
        A("")
        A("| 责任单元 | 违规类型 | 证据 |")
        A("|---|---|---|")
        for a in anchors[:20]:
            A("| %s → %s | %s | %s |" % (a["accountable"], a["decision_unit"][:36],
                                        a["violation_type"], "；".join(a["evidence"])[:50]))
        A("")
    if acc:
        A("## 验收判分")
        A("")
        A("| 项 | 值 |")
        A("|---|---|")
        for k, v in acc.items():
            A("| %s | %s |" % (k, v))
        A("")
    A("## 边界")
    A("")
    A("- 本报告只做**结构化可判定**的四类：时空冲突、状态互斥、时间倒退、伏笔未回收。")
    A("- 认知越界与性格 OOC 需外部知识（角色知识图谱/画像），**不在本编排器范围内**。")
    A("- 输入质量决定输出质量：坐标缺失即跳过，抽取层漏抽则此处无从检出。")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nodes", required=True, help="EventNode JSON 路径")
    ap.add_argument("--accept", action="store_true", help="验收模式（样本带 gold 标注）")
    ap.add_argument("--out-json", default=None)
    ap.add_argument("--out-md", default=None)
    args = ap.parse_args()

    mod = load_engine()
    nodes = load_nodes(args.nodes)
    print("载入 %d 个 EventNode，角色 %d 个" % (len(nodes), len({n.character for n in nodes})))
    results = LV.run_all(mod, nodes)
    print("冲突总数:", results["total_conflicts"],
          "| 各校验器:", {k: len(results[k].get("conflicts", [])) for k in LV.VALIDATORS})
    anchors = anchor(nodes, results)
    acc = accept(nodes, results) if args.accept else None
    if acc:
        print("验收: 金样组 %d，检出 %d，召回率 %s" % (
            acc["gold_groups"], acc["detected_groups"], acc["recall"]))
        if acc["missed"]:
            print("未检出组:", acc["missed"])

    out_json = args.out_json or os.path.join(
        HERE, "corpus_audit", "logic_gaps_result.json")
    out_md = args.out_md or os.path.join(
        HERE, "corpus_audit", "logic_gaps_report.md")
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({"nodes": len(nodes), "results": results,
                   "anchors": anchors, "acceptance": acc,
                   "schema": schema_doc()}, f, ensure_ascii=False, indent=1)
    write_md(nodes, results, anchors, out_md, acc)
    print("报告:", out_md)
    print("数据:", out_json)


if __name__ == "__main__":
    main()

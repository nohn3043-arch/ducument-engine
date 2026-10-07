"""《水浒传》语义级漏洞审计驱动（B2：引擎内置 OpenAIProvider + 逐回语义诊断）。

这是 `shuihu_audit_report.py`（离线规则层）的**互补通道**：规则层只能做机械一致性
检查，对古典章回白话抓不到语义级漏洞；本脚本改用引擎内置的 `OpenAIProvider` 把
每一回原文交给 LLM，按引擎的漏洞分类法做语义审计，产出可定位原文的漏洞清单。

依赖：仅本仓库引擎（零第三方依赖）。需要任意 OpenAI 兼容端点。

用法（设置环境变量后运行）：
    set SHUIHU_API_KEY=sk-xxxx
    set SHUIHU_BASE_URL=https://api.openai.com/v1   # 可选，默认 OpenAI
    set SHUIHU_MODEL=gpt-4o-mini                  # 可选，默认 gpt-4o-mini
    set SHUIHU_LIMIT=5                            # 可选，先小批量试跑
    python shuihu_llm_audit.py

输出：corpus_audit/水浒传_LLM漏洞审计.md
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import glob

ROOT = os.path.dirname(os.path.abspath(__file__))
ENG_FILE = os.path.join(ROOT, "Story Engine for Creator.py")
CORPUS = os.path.join(ROOT, "corpus", "水浒传")
OUT = os.path.join(ROOT, "corpus_audit", "水浒传_LLM漏洞审计.md")
CH_RE = re.compile(r"^(\d{3})\s+(.+?)\.txt$")
MAX_CHARS = int(os.environ.get("SHUIHU_MAX_CHARS", "9000"))  # 每回送审截断，控 token

RUBRIC = """你是长篇叙事一致性审计专家。请对下面这一段《水浒传》原文做**漏洞审查**。
只关注客观可定位的逻辑/事实矛盾，不要做主观文评。请逐条检查以下维度：
1) 人物一致性：身份、关系、生死、姓名前后矛盾（如已死之人又出场、同一人两种说法）
2) 因果自洽：动机→行为→结果断裂，或"无来由"的转折
3) 时空/地理：同一时刻身处两地、距离与时间明显不合理
4) 时间线/年龄：年龄倒退、时序错乱、追述与在场混淆
5) 性格 OOC：行为明显违背该角色既定性格/前文人设
6) 设定/制度硬伤：宋代官职、礼制、地理、兵器、习俗等明显时代错误或前后不一
7) 伏笔/呼应断裂：前文埋设与后文收束矛盾或落空

【严格收录纪律，违反则视为误报】
- 只收录你**确认存在**的客观矛盾。下列情况**不要**收录：
  ① 人物故意隐瞒身份（如王进假称姓张）属正常叙事手法；
  ② 后文补叙/倒叙前文（如高俅与王升旧仇）属正常写法；
  ③ 叙事留白或伏笔未明收束但本身不构成矛盾；
  ④ 与史实相符的内容。
- 不要为凑数收录非矛盾项；拿不准就丢弃。
- severity 必须与 explanation 自洽：仅确为硬性矛盾且无合理解释时评"高"；明显轻微或存疑评"低"；其余"中"。

严格只输出 JSON，不要任何额外文字，格式：
{"findings":[{"type":维度编号或名称,"severity":"高|中|低","scope":"internal|historical|textual","quote":"原文可定位片段(<=40字)","explanation":"矛盾点说明"}]}
说明：scope 取值 internal=小说内部前后矛盾；historical=与宋代史实/制度不符；textual=文本讹误或文义不通。
若本回未发现漏洞，返回 {"findings":[]}。

【输出长度纪律】
quote 严格 <=40 字；explanation 严格 <=60 字。言简意赅，避免超长导致输出被截断。"""


def load_engine():
    spec = importlib.util.spec_from_file_location("creator_engine", ENG_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def extract_json(text: str):
    """从 LLM 回复里抠出第一个 JSON 对象（容忍 markdown 包裹）。"""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def main() -> int:
    key = os.environ.get("SHUIHU_API_KEY")
    if not key:
        print("缺少 SHUIHU_API_KEY —— 请先设置环境变量（见文件头用法）。不消耗任何额度。")
        return 1
    base_url = os.environ.get("SHUIHU_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("SHUIHU_MODEL", "gpt-4o-mini")
    limit = int(os.environ.get("SHUIHU_LIMIT", "0"))

    eng = load_engine()
    llm = eng.OpenAIProvider(api_key=key, model=model, base_url=base_url)
    cache_dir = os.path.join(ROOT, "corpus_audit", "_llm_cache")
    os.makedirs(cache_dir, exist_ok=True)

    files = sorted(glob.glob(os.path.join(CORPUS, "*.txt")))
    if limit:
        files = files[:limit]

    all_findings = []
    cached = 0
    for path in files:
        fn = os.path.basename(path)
        m = CH_RE.match(fn)
        idx = m.group(1) if m else "???"
        title = m.group(2) if m else fn
        cache_path = os.path.join(cache_dir, "%s.json" % idx)
        # 断点续跑：已缓存且有效则跳过 API 调用
        if os.path.exists(cache_path):
            try:
                cached_data = json.load(open(cache_path, encoding="utf-8"))
                for f in cached_data:
                    all_findings.append(f)
                cached += 1
                print("  第%s回：缓存 %d 条" % (idx, len(cached_data)))
                continue
            except Exception:
                pass
        text = open(path, encoding="utf-8-sig").read().strip()
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS] + "\n…（截断）"
        prompt = RUBRIC + "\n\n【第%s回 %s】\n%s" % (idx, title, text)
        try:
            resp = llm.generate(prompt, temperature=0.2, max_tokens=4000)
        except Exception as e:  # noqa: BLE001
            print("  第%s回调用失败：%s" % (idx, e))
            continue
        data = extract_json(resp)
        if not data or "findings" not in data:
            print("  第%s回：未解析到 JSON（原始回复前80字: %s）"
                  % (idx, resp[:80].replace("\n", " ")))
            continue
        chapter_findings = []
        for f in data["findings"]:
            f["chapter"] = int(idx)
            f["chapter_title"] = title
            chapter_findings.append(f)
            all_findings.append(f)
        try:
            json.dump(chapter_findings, open(cache_path, "w", encoding="utf-8"),
                      ensure_ascii=False)
        except Exception:
            pass
        print("  第%s回：%d 条" % (idx, len(chapter_findings)))

    sev_order = {"高": 0, "中": 1, "低": 2}
    all_findings.sort(key=lambda x: (sev_order.get(x.get("severity", "低"), 3),
                                     x.get("chapter", 0)))
    by_type: dict = {}
    for f in all_findings:
        by_type.setdefault(f.get("type", "其他"), []).append(f)

    L = []
    A = L.append
    A("# 《水浒传》语义级漏洞审计（B2 · 引擎 LLM 通道）")
    A("")
    A("工具：`Story Engine for Creator.py` 内置 `OpenAIProvider` + 逐回语义诊断。")
    A("模型：%s　端点：%s" % (model, base_url))
    A("送审回数：%d　命中漏洞：%d" % (len(files), len(all_findings)))
    scope_cnt = {}
    for f in all_findings:
        scope_cnt[f.get("scope", "其他")] = scope_cnt.get(f.get("scope", "其他"), 0) + 1
    A("范围分布：%s" % "、".join("%s %d" % (k, v) for k, v in sorted(scope_cnt.items())))
    A("")
    A("> 本审计覆盖**语义级**矛盾（人物/因果/时空/时间线/性格/制度/伏笔），")
    A("> 与离线规则层（corpus_audit/水浒传_审计报告.md）互补——规则层查机械一致性，")
    A("> 本层查其抓不到的语义漏洞。scope：internal=小说内部前后矛盾 / historical=与宋代史实制度不符 / textual=文本讹误。")
    A("")
    A("## 按严重度排序")
    A("")
    A("| 严重度 | 回目 | 类型 | 范围 | 原文片段 | 说明 |")
    A("|---|---|---|---|---|---|")
    for f in all_findings:
        A("| %s | 第%s回 %s | %s | %s | %s | %s |" % (
            f.get("severity", ""),
            f.get("chapter", ""), f.get("chapter_title", ""),
            f.get("type", ""), f.get("scope", ""),
            (f.get("quote", "") or "").replace("|", "/"),
            (f.get("explanation", "") or "").replace("|", "/"),
        ))
    A("")
    A("## 按范围聚合")
    A("")
    by_scope: dict = {}
    for f in all_findings:
        by_scope.setdefault(f.get("scope", "其他"), []).append(f)
    for s, items in sorted(by_scope.items(), key=lambda kv: -len(kv[1])):
        A("### %s（%d 条）" % (s, len(items)))
        A("")
        for f in items:
            A("- 第%s回 %s【%s·%s】%s — %s" % (
                f.get("chapter", ""), f.get("chapter_title", ""),
                f.get("severity", ""), f.get("type", ""),
                (f.get("quote", "") or "").replace("\n", " "),
                (f.get("explanation", "") or "").replace("\n", " "),
            ))
        A("")
    A("## 按类型聚合")
    A("")
    for t, items in sorted(by_type.items(), key=lambda kv: -len(kv[1])):
        A("### %s（%d 条）" % (t, len(items)))
        A("")
        for f in items:
            A("- 第%s回 %s【%s·%s】%s — %s" % (
                f.get("chapter", ""), f.get("chapter_title", ""),
                f.get("severity", ""), f.get("scope", ""),
                (f.get("quote", "") or "").replace("\n", " "),
                (f.get("explanation", "") or "").replace("\n", " "),
            ))
        A("")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    print("\n已生成 %s（%d 条漏洞）" % (OUT, len(all_findings)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

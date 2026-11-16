/* 合同审查引擎 · 交互测试页 app.js
 *
 * 加载方式：页面通过 fetch 从同仓库取引擎源码（compliance_engine/*.py）
 * 与规则 JSON（rules/*.json、rules/en/*.json），写入 Pyodide 虚拟文件系统
 * 后运行。本文件不复制引擎代码；引擎的唯一来源仍是 compliance_engine/。
 * 部署时（GitHub Actions）把 compliance_engine/ 复制到发布产物根目录，
 * 因此优先尝试同目录下的 compliance_engine/，再尝试上一级的
 * ../compliance_engine/（本地开发时 document-engine/ 为根目录的情况）。
 */
"use strict";

const PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js";

const ENGINE_PY = [
  "__init__.py", "engine.py", "rules.py", "auditors.py", "models.py", "report.py",
];
const RULE_JSON = [
  "common.json", "contract.json", "regulation.json", "official_doc.json",
];

const I18N = {
  zh: {
    title: "合同审查引擎 · 交互测试",
    subtitle: "粘贴合同、制度或公文，点“开始审查”，引擎在你的浏览器里跑出评分与逐条结论。",
    privacy: "🔒 隐私：审查全程在本地浏览器内完成（Pyodide 运行 Python 引擎），文本不会上传到任何服务器。",
    lblType: "文书类型", typeContract: "合同", typeRegulation: "制度", typeOfficial: "公文",
    lblLang: "审查语言", langAuto: "自动判定",
    lblUi: "界面语言 / UI",
    loading: "正在加载引擎（首次需下载 Pyodide，约 10–20 秒）…",
    ready: "引擎已就绪，可以开始审查。",
    loadFail: "引擎加载失败：",
    sampleZh: "填入中文合同示例", sampleEn: "填入英文合同示例", sampleLe02: "填入英文 LE02 政策摘要",
    placeholder: "在此粘贴要审查的文本…",
    run: "开始审查", selftest: "跑引擎自检", clear: "清空",
    empty: "请先粘贴要审查的文本。",
    running: "审查中…",
    scoreLabel: "评分 / 100", pass: "通过", fail: "不通过",
    findingsCount: (n) => `发现 ${n} 条`,
    noFindings: "未发现问题。",
    suggestion: "建议：", location: "位置：",
    downloadJson: "下载 JSON 报告",
    testTitle: "引擎自检",
    testRunning: "自检中…",
    foot1: "引擎：story-engine 仓库 document-engine/compliance_engine（纯 Python 标准库，零第三方依赖；规则库 rules/*.json 与 rules/en/*.json）。判定为决定论式：命中即判定，不输出概率。",
    foot2: "加载方式：页面通过 fetch 取同仓库的引擎源码与规则 JSON，写入 Pyodide 虚拟文件系统后运行；本页不复制引擎代码，不改动引擎。",
  },
  en: {
    title: "Document Review Engine · Interactive Test",
    subtitle: "Paste a contract, policy or official document and click “Run audit”. The engine runs entirely in your browser and returns a score with findings.",
    privacy: "🔒 Privacy: the audit runs locally in your browser (Python engine via Pyodide). Your text is never uploaded to any server.",
    lblType: "Document type", typeContract: "Contract", typeRegulation: "Policy / Regulation", typeOfficial: "Official document",
    lblLang: "Audit language", langAuto: "Auto-detect",
    lblUi: "UI language",
    loading: "Loading engine (first load downloads Pyodide, ~10–20 s)…",
    ready: "Engine ready. You can run an audit now.",
    loadFail: "Engine failed to load: ",
    sampleZh: "Load Chinese contract sample", sampleEn: "Load English contract sample", sampleLe02: "Load English LE02 policy excerpt",
    placeholder: "Paste the text to audit here…",
    run: "Run audit", selftest: "Run engine self-test", clear: "Clear",
    empty: "Please paste some text to audit first.",
    running: "Auditing…",
    scoreLabel: "Score / 100", pass: "PASS", fail: "FAIL",
    findingsCount: (n) => `${n} finding(s)`,
    noFindings: "No issues found.",
    suggestion: "Suggestion: ", location: "Location: ",
    downloadJson: "Download JSON report",
    testTitle: "Engine self-test",
    testRunning: "Running self-test…",
    foot1: "Engine: document-engine/compliance_engine from the story-engine repo (pure Python standard library, zero third-party dependencies; rule libraries rules/*.json and rules/en/*.json). Deterministic verdicts: a hit is a verdict, no probabilities.",
    foot2: "Loading: this page fetches the engine source and rule JSON files from the same repo, writes them into Pyodide's virtual filesystem, and runs them. No engine code is duplicated in this page.",
  },
};

const SAMPLES = {
  zhContract: `采购合同

甲方：星辰科技有限公司
乙方：云帆供应链有限公司

第一条 合同标的
甲方向乙方采购办公设备一批，标的为办公设备及配套服务。

第二条 价款与支付
合同总价款为人民币200000元。甲方应于验收合格后30日内支付。
乙方应于收到款项后5日内开具发票。

第三条 履行期限
乙方应于2026年9月30日前完成交付。

第四条 违约责任
违约金为50000元。
若乙方逾期交付，违约金为80000元。
乙方加班无补偿，需自行安排进度。

第五条 争议解决
因本合同产生的争议，双方协商解决；协商不成的，提交甲方所在地人民法院诉讼。

第六条 其他
本合同最终解释权归甲方所有。
甲方有权调整交付计划，甲方有权变更验收标准，甲方有权单方解除合同。
乙方应尽快完成交付。`,
  enContract: `Service Agreement
1. Parties. This agreement is entered into between Party A and Party B.
2. Subject matter. Party B shall provide software services and deliverables.
3. Price. The total amount payable is USD 50,000. Payment is due within
30 days. The term of this agreement is 12 months, with completion by
31 December 2026.
4. Deposit. Party B shall pay a security deposit of USD 5,000.
5. Liquidated damages. If Party B is in breach, liquidated damages shall
be 50% of the contract amount. Party A has the final right of
interpretation and Party B shall not be liable for any delay. Party B
shall complete the work in a timely manner.
6. Dispute resolution. Any dispute shall be submitted to arbitration.`,
  le02: `Signing Process Policy
1 Document overview
2 Executive Summary
This policy talks about when dual signature is needed and the approvals
needed for various payments, transactions and donations. The main purpose
of this policy is to set out who may sign on behalf of the company.
3 Signing Process Policy
All companies under the umbrella of the holding company, msg global
solutions ag (Switzerland) are required to respect the same principles
for signing documents. This Signing Policy applies to any other companies
in which msg global may become majority owner.
The Executive Board of msg global regularly reviews this Signing Policy
and is responsible for making any revisions or clarifications as warranted.
4 Dual Signatures (Four Eyes Principle)
All contract documents need to be signed by two (2) persons, who are
authorized to represent their respective company. Only in exceptional
circumstances would it be possible for only one of the authorized
representatives to sign a contract on his own, and only within the limits
of their power of attorney and as long as he has obtained the written
approval of the other representative. This principle always ensures that
two persons will have reviewed, read and understood the contracts.
6.2 Approval Matrix for Customer Contracts
The below table shows the Review and Approval Process for Proposal and
Contracts. Amounts above 100,000 EUR require process approval and review
of all relevant parties listed. The Head of Marketing is able to sign any
kind of contract related to Marketing activities if necessary, and the
Legal Department must be notified in a timely manner, etc.
19 Effective Date
This update of the policy will be effective from 01 November 2022.`,
};

const $ = (id) => document.getElementById(id);
let uiLang = "zh";
let pyodide = null;
let auditJson = null;
let selftestFn = null;
let lastReportJson = "";

function t(key) {
  const v = I18N[uiLang][key];
  return typeof v === "function" ? v : v;
}

function applyI18n() {
  document.documentElement.lang = uiLang === "zh" ? "zh-CN" : "en";
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const v = I18N[uiLang][el.dataset.i18n];
    if (typeof v === "string") el.textContent = v;
  });
  document.querySelectorAll("[data-i18n-ph]").forEach((el) => {
    const v = I18N[uiLang][el.dataset.i18nPh];
    if (typeof v === "string") el.placeholder = v;
  });
}

function setStatus(msg, cls) {
  const el = $("status");
  el.textContent = msg;
  el.className = cls || "";
}

const BOOTSTRAP_PY = `
import sys, json
sys.path.insert(0, "/engine")
from compliance_engine import ComplianceEngine
from compliance_engine.models import DocType
from compliance_engine.report import to_json
from compliance_engine.rules import RuleEngine, detect_language

_engine = ComplianceEngine()

def audit_json(text, doc_type, lang):
    lang_arg = None if lang in ("auto", "", None) else lang
    report = _engine.audit(text, DocType.from_str(doc_type), lang=lang_arg)
    return to_json(report)

def selftest():
    out = []
    def check(name, fn):
        try:
            ok = bool(fn())
        except Exception:
            ok = False
        out.append({"name": name, "ok": ok})
    check("zh rules: 14 loaded", lambda: len(RuleEngine(lang="zh").rules) == 14)
    check("en rules: 14 loaded", lambda: len(RuleEngine(lang="en").rules) == 14)
    check("detect_language(en sample) == en",
          lambda: detect_language(SAMPLES_EN_CONTRACT) == "en")
    check("zh contract hits CT-004 (no overtime pay)",
          lambda: any(f.rule_id == "CT-004" for f in
              ComplianceEngine().audit(SAMPLES_ZH_CONTRACT, DocType.CONTRACT).findings))
    check("en contract hits CT-003 (50% damages)",
          lambda: any(f.rule_id == "CT-003" for f in
              ComplianceEngine().audit(SAMPLES_EN_CONTRACT, DocType.CONTRACT).findings))
    check("LE02 regulation scores >= 50 (was 10 before en rules)",
          lambda: ComplianceEngine().audit(SAMPLES_LE02, DocType.REGULATION).overall_score >= 50)
    return json.dumps(out, ensure_ascii=False)
`;

async function fetchText(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status} for ${url}`);
  return await r.text();
}

async function findEngineBase() {
  for (const base of ["compliance_engine/", "../compliance_engine/"]) {
    try {
      await fetchText(base + "__init__.py");
      return base;
    } catch (e) { /* try next */ }
  }
  throw new Error("cannot fetch compliance_engine/ from either compliance_engine/ or ../compliance_engine/");
}

async function loadEngine() {
  try {
    pyodide = await loadPyodide();
    const base = await findEngineBase();
    const files = [];
    for (const f of ENGINE_PY) files.push(["compliance_engine/" + f, base + f]);
    for (const f of RULE_JSON) {
      files.push(["compliance_engine/rules/" + f, base + "rules/" + f]);
      files.push(["compliance_engine/rules/en/" + f, base + "rules/en/" + f]);
    }
    pyodide.FS.mkdirTree("/engine/compliance_engine/rules/en");
    for (const [dest, url] of files) {
      const text = await fetchText(url);
      pyodide.FS.writeFile("/engine/" + dest, text);
    }
    // Samples are embedded in this page; hand them to Python for self-test.
    pyodide.globals.set("SAMPLES_ZH_CONTRACT", SAMPLES.zhContract);
    pyodide.globals.set("SAMPLES_EN_CONTRACT", SAMPLES.enContract);
    pyodide.globals.set("SAMPLES_LE02", SAMPLES.le02);
    await pyodide.runPythonAsync(BOOTSTRAP_PY);
    auditJson = pyodide.globals.get("audit_json");
    selftestFn = pyodide.globals.get("selftest");
    setStatus(t("ready"), "ready");
    $("run").disabled = false;
    $("selftest").disabled = false;
  } catch (e) {
    setStatus(t("loadFail") + e.message, "error");
    console.error(e);
  }
}

function esc(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function renderReport(report) {
  $("resultCard").hidden = false;
  $("scoreNum").textContent = Math.round(report.overall_score);
  const v = $("verdict");
  v.textContent = report.passed ? t("pass") : t("fail");
  v.className = "verdict " + (report.passed ? "pass" : "fail");
  const sev = report.summary.by_severity || {};
  $("counts").textContent =
    t("findingsCount")(report.summary.total_findings) +
    Object.entries(sev).map(([k, n]) => ` · ${k} ${n}`).join("");
  const box = $("findings");
  if (!report.findings.length) {
    box.innerHTML = `<p>${esc(t("noFindings"))}</p>`;
    return;
  }
  box.innerHTML = report.findings.map((f) => `
    <div class="finding">
      <span class="pill ${esc(f.severity)}">${esc(f.severity)}</span>
      <span class="pill">${esc(f.rule_id)}</span>
      <span class="meta">${esc(f.category)} · ${esc(t("location"))} ${esc(f.location)}</span>
      <div class="msg">${esc(f.message)}</div>
      ${f.suggestion ? `<div class="sug">${esc(t("suggestion"))}${esc(f.suggestion)}</div>` : ""}
      ${f.snippet ? `<div class="snip">${esc(f.snippet)}</div>` : ""}
    </div>`).join("");
}

$("run").addEventListener("click", () => {
  const text = $("input").value.trim();
  if (!text) { alert(t("empty")); return; }
  $("run").disabled = true;
  setStatus(t("running"));
  setTimeout(() => {
    try {
      const jsonStr = auditJson(text, $("docType").value, $("lang").value);
      lastReportJson = jsonStr;
      renderReport(JSON.parse(jsonStr));
      setStatus(t("ready"), "ready");
    } catch (e) {
      setStatus(t("loadFail") + e.message, "error");
      console.error(e);
    } finally {
      $("run").disabled = false;
    }
  }, 30);
});

$("selftest").addEventListener("click", () => {
  $("testCard").hidden = false;
  $("testList").innerHTML = `<li>${esc(t("testRunning"))}</li>`;
  setTimeout(() => {
    try {
      const results = JSON.parse(selftestFn());
      const passed = results.filter((r) => r.ok).length;
      $("testList").innerHTML = results.map((r) =>
        `<li class="${r.ok ? "ok" : "bad"}">${r.ok ? "✓" : "✗"} ${esc(r.name)}</li>`
      ).join("") + `<li><strong>${passed}/${results.length}</strong></li>`;
    } catch (e) {
      $("testList").innerHTML = `<li class="bad">✗ ${esc(e.message)}</li>`;
    }
  }, 30);
});

$("downloadJson").addEventListener("click", () => {
  if (!lastReportJson) return;
  const blob = new Blob([lastReportJson], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "audit-report.json";
  a.click();
  URL.revokeObjectURL(a.href);
});

$("clear").addEventListener("click", () => {
  $("input").value = "";
  $("resultCard").hidden = true;
});

$("sampleZh").addEventListener("click", () => {
  $("input").value = SAMPLES.zhContract;
  $("docType").value = "contract"; $("lang").value = "auto";
});
$("sampleEn").addEventListener("click", () => {
  $("input").value = SAMPLES.enContract;
  $("docType").value = "contract"; $("lang").value = "auto";
});
$("sampleLe02").addEventListener("click", () => {
  $("input").value = SAMPLES.le02;
  $("docType").value = "regulation"; $("lang").value = "auto";
});
$("uiLang").addEventListener("change", (e) => {
  uiLang = e.target.value;
  applyI18n();
  if (pyodide) setStatus(t("ready"), "ready");
});

applyI18n();
loadEngine();

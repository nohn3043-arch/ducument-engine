"""报告生成：HTML（可视化）/ JSON（结构化）/ Markdown（简洁）。

HTML 报告内嵌样式，单文件可分享；JSON 供系统集成；Markdown 供文档归档。
"""

import json
from typing import Any, Dict

from .models import AuditReport, RiskLevel

_SEV_COLOR = {
    RiskLevel.FATAL: "#dc2626",
    RiskLevel.CRITICAL: "#ea580c",
    RiskLevel.WARNING: "#d97706",
    RiskLevel.SAFE: "#16a34a",
}

# 报告外壳文案：HTML/Markdown 的标题与固定文案按报告语言区分。
# JSON 字段名不受影响（to_dict 不变）；trace 备注仍为引擎内部日志原文。
_STRINGS = {
    "zh": {
        "lang_attr": "zh",
        "colon": "：",
        "lp": "（",
        "rp": "）",
        "title": "文书合规审计报告",
        "doc_type": "文书类型",
        "score": "综合评分",
        "verdict": "判定",
        "pass": "通过",
        "fail": "不通过",
        "type": "类型",
        "responsibility": "责任节点",
        "time": "时间",
        "audit_time": "审计时间",
        "summary": "汇总",
        "total_findings": "发现总数",
        "by_severity": "按严重度",
        "by_category": "按维度",
        "findings": "问题清单",
        "trace": "审计追溯链",
        "no_issues": "未发现合规问题。",
        "hit": "命中",
        "location": "位置",
        "suggestion": "建议",
        "none": "无",
        "list_sep": "、",
        "sev": {
            RiskLevel.FATAL: "致命",
            RiskLevel.CRITICAL: "严重",
            RiskLevel.WARNING: "警告",
            RiskLevel.SAFE: "安全",
        },
    },
    "en": {
        "lang_attr": "en",
        "colon": ": ",
        "lp": " (",
        "rp": ")",
        "title": "Document Compliance Audit Report",
        "doc_type": "Document type",
        "score": "Overall score",
        "verdict": "Verdict",
        "pass": "Pass",
        "fail": "Fail",
        "type": "Type",
        "responsibility": "Responsibility",
        "time": "Generated at",
        "audit_time": "Audit time",
        "summary": "Summary",
        "total_findings": "Total findings",
        "by_severity": "By severity",
        "by_category": "By category",
        "findings": "Findings",
        "trace": "Audit trace",
        "no_issues": "No compliance issues found.",
        "hit": "Match",
        "location": "Location",
        "suggestion": "Suggestion",
        "none": "None",
        "list_sep": ", ",
        "sev": {
            RiskLevel.FATAL: "Fatal",
            RiskLevel.CRITICAL: "Critical",
            RiskLevel.WARNING: "Warning",
            RiskLevel.SAFE: "Safe",
        },
    },
}


def _strings(report: AuditReport) -> Dict[str, Any]:
    lang = getattr(report, "lang", "zh") or "zh"
    return _STRINGS.get(lang, _STRINGS["zh"])


def _sev_label(severity: RiskLevel, t: Dict[str, Any]) -> str:
    return t["sev"][severity]


def to_dict(report: AuditReport) -> Dict[str, Any]:
    return {
        "doc_type": report.doc_type.value,
        "title": report.title,
        "overall_score": report.overall_score,
        "passed": report.passed,
        "generated_at": report.generated_at,
        "summary": report.summary,
        "responsibility": {
            "organization": report.responsibility.organization,
            "role": report.responsibility.role,
            "stage": report.responsibility.stage,
            "trace_chain": report.responsibility.trace_chain,
        },
        "findings": [
            {
                "rule_id": f.rule_id,
                "category": f.category,
                "severity": f.severity.name,
                "message": f.message,
                "suggestion": f.suggestion,
                "location": f.location,
                "snippet": f.snippet,
            }
            for f in report.findings
        ],
        "trace": [
            {
                "timestamp": t.timestamp,
                "operation": t.operation,
                "stage": t.stage,
                "node_id": t.node_id,
                "remark": t.remark,
            }
            for t in report.trace
        ],
    }


def to_json(report: AuditReport) -> str:
    return json.dumps(to_dict(report), ensure_ascii=False, indent=2)


def to_markdown(report: AuditReport) -> str:
    t = _strings(report)
    lines = [
        f"# {t['title']}{t['colon']}{report.title}",
        "",
        f"- {t['doc_type']}{t['colon']}{report.doc_type.value}",
        f"- {t['score']}{t['colon']}{report.overall_score:.0f} / 100",
        f"- {t['verdict']}{t['colon']}{t['pass'] if report.passed else t['fail']}",
        f"- {t['audit_time']}{t['colon']}{report.generated_at}",
        f"- {t['responsibility']}{t['colon']}{report.responsibility.organization} / {report.responsibility.role}",
        "",
        f"## {t['summary']}",
        "",
        f"- {t['total_findings']}{t['colon']}{report.summary.get('total_findings', 0)}",
        f"- {t['by_severity']}{t['colon']}{_fmt_dict(report.summary.get('by_severity', {}), t)}",
        f"- {t['by_category']}{t['colon']}{_fmt_dict(report.summary.get('by_category', {}), t)}",
        "",
        f"## {t['findings']}",
        "",
    ]
    if not report.findings:
        lines.append(t["no_issues"])
    for f in sorted(report.findings, key=lambda x: x.severity.value):
        lines.append(
            f"- **[{_sev_label(f.severity, t)}] {f.category}** {f.message}"
            f"\n  - {t['location']}{t['colon']}{f.location} | {t['hit']}{t['colon']}`{f.snippet or '—'}`"
            f"\n  - {t['suggestion']}{t['colon']}{f.suggestion}"
        )
    lines += ["", f"## {t['trace']}", ""]
    for t_ in report.trace:
        lines.append(f"- `{t_.timestamp}` {t_.operation} | {t_.remark}")
    return "\n".join(lines)


def to_html(report: AuditReport) -> str:
    t = _strings(report)
    sev_counts = report.summary.get("by_severity", {})
    cards = "".join(
        f'<span class="sev sev-{s.name.lower()}" style="background:{_SEV_COLOR[s]}">{_sev_label(s, t)} {sev_counts.get(s.name, 0)}</span>'
        for s in (RiskLevel.FATAL, RiskLevel.CRITICAL, RiskLevel.WARNING)
    )
    findings_html = ""
    for f in sorted(report.findings, key=lambda x: x.severity.value):
        findings_html += f"""
<div class="finding sev-{f.severity.name.lower()}">
  <div class="f-head">
    <span class="badge" style="background:{_SEV_COLOR[f.severity]}">{_sev_label(f.severity, t)}</span>
    <strong>{f.category}</strong>
    <span class="rule">{f.rule_id}</span>
  </div>
  <p class="f-msg">{f.message}</p>
  <p class="f-snip">{t['hit']}{t['colon']}<code>{f.snippet or '—'}</code></p>
  <p class="f-loc">{t['location']}{t['colon']}{f.location}</p>
  <p class="f-sug">{t['suggestion']}{t['colon']}{f.suggestion}</p>
</div>"""
    if not report.findings:
        findings_html = f'<div class="finding sev-safe"><p class="f-msg">{t["no_issues"]}</p></div>'
    trace_html = "".join(
        f"<li><code>{tr.timestamp}</code> {tr.operation} — {tr.remark}</li>"
        for tr in report.trace
    )
    return f"""<!DOCTYPE html>
<html lang="{t['lang_attr']}">
<head>
<meta charset="UTF-8">
<title>{t['title']} · {report.title}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif; margin: 0; background: #f4f5f7; color: #1f2937; }}
.wrap {{ max-width: 900px; margin: 0 auto; padding: 32px 20px; }}
h1 {{ font-size: 24px; border-bottom: 3px solid #2563eb; padding-bottom: 12px; }}
.meta {{ display: flex; gap: 24px; flex-wrap: wrap; margin: 16px 0; color: #4b5563; font-size: 14px; }}
.score-box {{ background: #fff; border-radius: 12px; padding: 20px; margin: 16px 0; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
.score {{ font-size: 42px; font-weight: 700; color: #2563eb; }}
.verdict {{ font-size: 16px; font-weight: 600; }}
.verdict.pass {{ color: #16a34a; }} .verdict.fail {{ color: #dc2626; }}
.sev {{ color: #fff; padding: 3px 10px; border-radius: 12px; font-size: 13px; margin-right: 8px; }}
h2 {{ font-size: 18px; margin-top: 28px; }}
.finding {{ background: #fff; border-radius: 10px; padding: 14px 16px; margin: 10px 0; box-shadow: 0 1px 3px rgba(0,0,0,.06); border-left: 5px solid #9ca3af; }}
.finding.sev-fatal {{ border-left-color: #dc2626; }} .finding.sev-critical {{ border-left-color: #ea580c; }}
.finding.sev-warning {{ border-left-color: #d97706; }} .finding.sev-safe {{ border-left-color: #16a34a; }}
.f-head {{ display: flex; align-items: center; gap: 10px; }}
.badge {{ color: #fff; padding: 2px 8px; border-radius: 10px; font-size: 12px; }}
.rule {{ color: #9ca3af; font-size: 12px; }}
.f-msg {{ margin: 8px 0 4px; font-weight: 600; }}
.f-snip, .f-loc, .f-sug {{ margin: 3px 0; font-size: 13px; color: #4b5563; }}
code {{ background: #f3f4f6; padding: 1px 6px; border-radius: 4px; }}
ul.trace {{ background: #fff; border-radius: 10px; padding: 16px 16px 16px 36px; box-shadow: 0 1px 3px rgba(0,0,0,.06); font-size: 13px; color: #4b5563; }}
</style>
</head>
<body>
<div class="wrap">
<h1>{t['title']} · {report.title}</h1>
<div class="meta">
  <span>{t['type']}{t['colon']}{report.doc_type.value}</span>
  <span>{t['responsibility']}{t['colon']}{report.responsibility.organization} / {report.responsibility.role}</span>
  <span>{t['time']}{t['colon']}{report.generated_at}</span>
</div>
<div class="score-box">
  <div style="font-size:13px;color:#6b7280">{t['score']}</div>
  <div class="score">{report.overall_score:.0f}<span style="font-size:16px;color:#9ca3af"> / 100</span></div>
  <div class="verdict {'pass' if report.passed else 'fail'}">{t['verdict']}{t['colon']}{t['pass'] if report.passed else t['fail']}</div>
  <div style="margin-top:10px">{cards}</div>
</div>
<h2>{t['findings']}{t['lp']}{report.summary.get('total_findings', 0)}{t['rp']}</h2>
{findings_html}
<h2>{t['trace']}</h2>
<ul class="trace">{trace_html}</ul>
</div>
</body>
</html>"""


def _fmt_dict(d: Dict[str, Any], t: Dict[str, Any] = None) -> str:
    t = t or _STRINGS["zh"]
    if not d:
        return t["none"]
    return t["list_sep"].join(f"{k}={v}" for k, v in d.items())

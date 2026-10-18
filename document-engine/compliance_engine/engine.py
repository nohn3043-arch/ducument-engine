"""主引擎：编排审计流程、责任闭环锚定、评分与报告组装。

流程：分节 → 规则扫描 → 文档级审计 → 责任闭环 → 评分 → 报告。
全部判定为决定论式（命中即判定），不输出概率估计。
"""

import bisect
import re
from pathlib import Path
from typing import Dict, List, Optional

from .auditors import (
    BalanceAuditor,
    CompletenessAuditor,
    ConsistencyAuditor,
    FormatAuditor,
)
from .models import (
    AuditFinding,
    AuditNode,
    AuditReport,
    DocType,
    NodeStatus,
    ResponsibilityAccount,
    RiskLevel,
    TraceLog,
)
from .rules import RuleEngine

_SECTION_RE = re.compile(r"^(第[一二三四五六七八九十百千0-9]+[条款]|[0-9]+[.、．]|[一二三四五六七八九十]+[、．])")


class ComplianceEngine:
    def __init__(self, rules_dir: Optional[Path] = None):
        self.rule_engine = RuleEngine(rules_dir)
        self.account = ResponsibilityAccount(
            organization="Compliance-Core",
            role="ComplianceAuditor",
            stage="audit",
        )
        self.trace: List[TraceLog] = []

    def audit(
        self,
        text: str,
        doc_type: DocType,
        title: str = "",
    ) -> AuditReport:
        self.trace = []
        self.account.bind_stage("audit")
        self._log("START", None, f"启动审计：{doc_type.value}")

        nodes = self._segment(text)
        self._log("SEGMENT", None, f"文书分节完成：{len(nodes)} 个审计单元")

        findings: List[AuditFinding] = []
        findings.extend(self.rule_engine.scan(text, doc_type))
        self._log("RULE_SCAN", None, f"规则扫描命中：{len(findings)} 条")

        findings.extend(CompletenessAuditor().audit(text, doc_type))
        findings.extend(ConsistencyAuditor().audit(text, doc_type))
        findings.extend(BalanceAuditor().audit(text, doc_type))
        findings.extend(FormatAuditor().audit(text, doc_type))
        self._log("DOC_AUDIT", None, f"文档级审计完成：累计 {len(findings)} 条")

        findings = self._dedup(findings)
        self._attach_to_nodes(findings, nodes)

        score = self._score(findings)
        passed = score >= 60 and not any(
            f.severity in (RiskLevel.FATAL, RiskLevel.CRITICAL) for f in findings
        )
        summary = self._summarize(findings)
        self._log("SCORE", None, f"评分 {score:.0f}，判定 {'通过' if passed else '不通过'}")

        return AuditReport(
            doc_type=doc_type,
            title=title or "未命名文书",
            overall_score=score,
            passed=passed,
            findings=findings,
            nodes=nodes,
            trace=list(self.trace),
            responsibility=self.account,
            summary=summary,
        )

    # ---------- 内部流程 ----------
    def _segment(self, text: str) -> List[AuditNode]:
        nodes: List[AuditNode] = []
        current: List[str] = []
        current_section = "开头"
        block_start = -1
        block_end = 0
        pos = 0

        def flush():
            nonlocal current, block_start, block_end
            if current:
                nodes.append(
                    AuditNode(
                        node_id=f"N{len(nodes) + 1:03d}",
                        content="\n".join(current),
                        section=current_section,
                        status=NodeStatus.SCANNED,
                        start=max(block_start, 0),
                        end=block_end,
                    )
                )
                current = []
                block_start = -1

        for raw in text.splitlines(keepends=True):
            line_start = pos
            pos += len(raw)
            ln = raw.strip()
            if not ln:
                continue
            m = _SECTION_RE.match(ln)
            if m:
                flush()
                current_section = m.group(0).strip()
            if block_start < 0:
                block_start = line_start
            block_end = pos
            current.append(ln)
        flush()
        return nodes

    def _attach_to_nodes(self, findings: List[AuditFinding], nodes: List[AuditNode]) -> None:
        if not nodes:
            return
        starts = [n.start for n in nodes]
        for f in findings:
            if not f.snippet:
                continue
            node = None
            if f.offset >= 0:
                i = bisect.bisect_right(starts, f.offset) - 1
                if i >= 0 and f.offset < nodes[i].end:
                    node = nodes[i]
            if node is None:
                for candidate in nodes:
                    if f.snippet in candidate.content:
                        node = candidate
                        break
            if node is not None:
                node.findings.append(f)
                node.status = NodeStatus.AUDITED

    def _dedup(self, findings: List[AuditFinding]) -> List[AuditFinding]:
        seen = set()
        out: List[AuditFinding] = []
        for f in findings:
            key = (f.rule_id, f.message, f.snippet)
            if key in seen:
                continue
            seen.add(key)
            out.append(f)
        return out

    def _score(self, findings: List[AuditFinding]) -> float:
        score = 100.0
        for f in findings:
            if f.severity == RiskLevel.WARNING:
                score -= 5
            elif f.severity == RiskLevel.CRITICAL:
                score -= 15
            elif f.severity == RiskLevel.FATAL:
                score -= 30
        return max(0.0, score)

    def _summarize(self, findings: List[AuditFinding]) -> Dict[str, object]:
        by_severity: Dict[str, int] = {}
        by_category: Dict[str, int] = {}
        for f in findings:
            by_severity[f.severity.name] = by_severity.get(f.severity.name, 0) + 1
            by_category[f.category] = by_category.get(f.category, 0) + 1
        return {
            "total_findings": len(findings),
            "by_severity": by_severity,
            "by_category": by_category,
        }

    def _log(self, operation: str, node_id: Optional[str], remark: str) -> None:
        self.trace.append(
            TraceLog.now(operation=operation, stage="audit", node_id=node_id, remark=remark)
        )

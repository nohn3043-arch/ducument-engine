"""规则引擎：加载规则库（JSON）并按文书类型匹配。

规则库为纯 JSON 配置，可外部替换/扩展（--rules-dir）。
匹配为决定论式：命中即产出 finding，不输出概率。
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import AuditFinding, DocType, RiskLevel

_DEFAULT_RULES_DIR = Path(__file__).parent / "rules"

# 单条规则在一个文档内最多输出的命中数；超过后只保留一条汇总提示。
MAX_FINDINGS_PER_RULE = 200


class RuleEngine:
    def __init__(self, rules_dir: Optional[Path] = None):
        self.rules_dir = Path(rules_dir) if rules_dir else _DEFAULT_RULES_DIR
        self.rules: List[Dict[str, Any]] = []
        self._load_all()

    def _load_all(self) -> None:
        if not self.rules_dir.is_dir():
            raise FileNotFoundError(f"规则目录不存在: {self.rules_dir}")
        for f in sorted(self.rules_dir.glob("*.json")):
            self._load_file(f)

    def _load_file(self, path: Path) -> None:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        file_scope = data.get("doc_type")
        for rule in data.get("rules", []):
            rule = dict(rule)
            scope = rule.get("scope") or file_scope or "generic"
            rule["scope"] = scope
            self.rules.append(rule)

    def rules_for(self, doc_type: DocType) -> List[Dict[str, Any]]:
        return [r for r in self.rules if r.get("scope") in (doc_type.value, "generic")]

    def list_rules(self, doc_type: Optional[DocType] = None) -> List[Dict[str, Any]]:
        if doc_type is None:
            return list(self.rules)
        return self.rules_for(doc_type)

    def scan(self, text: str, doc_type: DocType) -> List[AuditFinding]:
        """对整篇文书做条款级扫描，返回全部命中 finding。"""
        findings: List[AuditFinding] = []
        for rule in self.rules_for(doc_type):
            findings.extend(self._apply(rule, text))
        return findings

    def _apply(self, rule: Dict[str, Any], text: str) -> List[AuditFinding]:
        kind = rule.get("kind", "risk_keywords")
        severity = _parse_severity(rule.get("severity", "WARNING"))
        if kind == "risk_keywords":
            return self._match_keywords(rule, text, severity)
        if kind == "forbidden_keywords":
            return self._match_keywords(rule, text, severity)
        if kind == "regex":
            return self._match_regex(rule, text, severity)
        return []

    def _match_keywords(
        self, rule: Dict[str, Any], text: str, severity: RiskLevel
    ) -> List[AuditFinding]:
        findings: List[AuditFinding] = []
        for kw in rule.get("patterns", []):
            if not kw:
                continue
            start = 0
            shown = 0
            while shown < MAX_FINDINGS_PER_RULE:
                idx = text.find(kw, start)
                if idx < 0:
                    break
                findings.append(
                    AuditFinding(
                        rule_id=rule["id"],
                        category=rule.get("category", "风险条款"),
                        severity=severity,
                        message=rule.get("message", f"命中风险词「{kw}」"),
                        suggestion=rule.get("suggestion", ""),
                        location="全文",
                        snippet=_snippet_at(text, idx, len(kw)),
                        offset=idx,
                    )
                )
                shown += 1
                start = idx + len(kw)
            total = text.count(kw)
            if total > shown:
                findings.append(
                    AuditFinding(
                        rule_id=rule["id"],
                        category=rule.get("category", "风险条款"),
                        severity=severity,
                        message=rule.get("message", f"命中风险词「{kw}」")
                        + f"（同词共 {total} 处，仅列前 {shown} 处）",
                        suggestion=rule.get("suggestion", ""),
                        location="全文",
                        snippet=kw,
                    )
                )
        return findings

    def _match_regex(
        self, rule: Dict[str, Any], text: str, severity: RiskLevel
    ) -> List[AuditFinding]:
        findings: List[AuditFinding] = []
        patterns = rule.get("patterns") or [rule.get("pattern", "")]
        matches = []
        for raw in patterns:
            if not raw:
                continue
            try:
                pat = re.compile(raw)
            except re.error:
                continue
            for m in pat.finditer(text):
                matches.append((m.start(), m.group(0)))
        matches.sort(key=lambda x: x[0])
        seen = set()
        for pos, value in matches:
            if pos in seen:
                continue
            seen.add(pos)
            if len(findings) >= MAX_FINDINGS_PER_RULE:
                findings.append(
                    AuditFinding(
                        rule_id=rule["id"],
                        category=rule.get("category", "格式规范"),
                        severity=severity,
                        message=rule.get("message", "命中规则模式")
                        + f"（同规则共 {len(matches)} 处，仅列前 {MAX_FINDINGS_PER_RULE} 处）",
                        suggestion=rule.get("suggestion", ""),
                        location="全文",
                        snippet=value,
                    )
                )
                break
            findings.append(
                AuditFinding(
                    rule_id=rule["id"],
                    category=rule.get("category", "格式规范"),
                    severity=severity,
                    message=rule.get("message", f"命中模式「{value}」"),
                    suggestion=rule.get("suggestion", ""),
                    location="全文",
                    snippet=_snippet_at(text, pos, len(value)),
                    offset=pos,
                )
            )
        return findings


def _parse_severity(s: str) -> RiskLevel:
    try:
        return RiskLevel[s.strip().upper()]
    except KeyError:
        return RiskLevel.WARNING


def _snippet_at(text: str, idx: int, length: int, radius: int = 18) -> str:
    if idx < 0:
        return ""
    start = max(0, idx - radius)
    end = min(len(text), idx + length + radius)
    return text[start:end]

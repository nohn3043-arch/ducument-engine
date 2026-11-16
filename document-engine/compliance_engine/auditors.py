"""文档级审计器：要素完整性 / 一致性 / 权利义务对等 / 公文格式。

与规则引擎（条款级命中）互补：这些审计需要整篇文书的跨段信息。
"""

import re
from typing import Dict, List

from .models import AuditFinding, DocType, RiskLevel

# 各文书类型的必备要素（关键词组，全部缺失任一即告警）
_COMPLETENESS: Dict[DocType, List[Dict[str, object]]] = {
    DocType.CONTRACT: [
        {"name": "当事人", "keywords": ["甲方", "乙方", "当事人"]},
        {"name": "标的", "keywords": ["标的", "项目", "服务", "货物", "产品"]},
        {"name": "价款", "keywords": ["价款", "金额", "费用", "价格", "报酬"]},
        {"name": "履行期限", "keywords": ["期限", "日期", "时间", "交付", "完成"]},
        {"name": "违约责任", "keywords": ["违约"]},
        {"name": "争议解决", "keywords": ["争议", "仲裁", "诉讼", "法院", "管辖"]},
    ],
    DocType.REGULATION: [
        {"name": "目的", "keywords": ["目的", "为规范", "为加强", "为进一步"]},
        {"name": "适用范围", "keywords": ["适用范围", "适用于", "本办法", "本制度"]},
        {"name": "职责", "keywords": ["职责", "负责", "承担"]},
        {"name": "流程", "keywords": ["流程", "程序", "步骤", "办理"]},
        {"name": "罚则", "keywords": ["罚则", "处罚", "奖惩", "责任追究", "考核"]},
        {"name": "生效条款", "keywords": ["生效", "施行", "发布之日起", "自发布"]},
    ],
    DocType.OFFICIAL_DOC: [
        {"name": "标题", "keywords": ["关于"]},
        {"name": "主送机关", "keywords": ["各", "单位", "部门", "处室"]},
        {"name": "成文日期", "keywords": ["年", "月", "日"]},
        {"name": "文号", "keywords": ["〔", "["]},
    ],
    DocType.GENERIC: [],
}

# 英文版必备要素：与中文版逐项对齐（同一要素的不同语言表达）。
# 关键词做大小写不敏感匹配；英文关键词用词干/短语以覆盖单复数与时态。
_COMPLETENESS_EN: Dict[DocType, List[Dict[str, object]]] = {
    DocType.CONTRACT: [
        {"name": "Parties", "keywords": ["party a", "party b", "the parties", "parties hereto"]},
        {"name": "Subject matter", "keywords": ["subject matter", "scope of work", "services", "goods", "products", "deliverables"]},
        {"name": "Price", "keywords": ["price", "amount", "fee", "fees", "payment", "consideration"]},
        {"name": "Term", "keywords": ["term", "duration", "delivery date", "deadline", "completion"]},
        {"name": "Liability for breach", "keywords": ["breach", "default", "liability"]},
        {"name": "Dispute resolution", "keywords": ["dispute", "arbitration", "litigation", "court", "jurisdiction", "governing law"]},
    ],
    DocType.REGULATION: [
        {"name": "Purpose", "keywords": ["purpose", "executive summary", "objective"]},
        {"name": "Scope", "keywords": ["scope", "applies to", "this policy", "this regulation"]},
        {"name": "Responsibilities", "keywords": ["responsib", "is responsible", "responsible for"]},
        {"name": "Procedure", "keywords": ["procedure", "process", "approval process", "steps"]},
        {"name": "Penalties", "keywords": ["penalt", "sanction", "disciplinary"]},
        {"name": "Effective date", "keywords": ["effective date", "effective from", "shall take effect", "comes into effect", "comes into force"]},
    ],
    DocType.OFFICIAL_DOC: [
        {"name": "Title", "keywords": ["re:", "subject:", "regarding"]},
        {"name": "Addressee", "keywords": ["to:", "dear", "all departments", "all staff"]},
        {"name": "Date of issue", "keywords": ["date", "dated"]},
        {"name": "Reference number", "keywords": ["ref", "reference no", "document no"]},
    ],
    DocType.GENERIC: [],
}

_MONTHS_EN = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)

_ASSIGN_RE = re.compile(
    r"([\u4e00-\u9fa5]{2,8})(?:为|是|：)([0-9]{2,}[年月日元%]|[一二三四五六七八九十百千]+[年月日元%])"
)

_EN_MONTHS = {
    name.lower(): i + 1
    for i, name in enumerate(
        ("January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December")
    )
}

# 英文赋值句：名词短语 + is/are/shall be/will be/equals/: + 数值型取值
# （金额 / 百分比 / 期限 / 日期）。取值必须以数字或日期开头，避免把
# "is required"、"is able to" 这类非数值表述误判为赋值。
_EN_VALUE_RE = (
    r"(?:"
    r"\d{1,2}\s+(?:" + _MONTHS_EN + r")\s+\d{4}"
    r"|\d{4}-\d{2}-\d{2}"
    r"|(?:" + _MONTHS_EN + r")\s+\d{1,2},?\s+\d{4}"
    r"|(?:usd|eur|gbp|cny|rmb|hkd|\$|€|£)?\s*\$?\d[\d,]*(?:\.\d+)?\s*"
    r"(?:%|percent|per\s+cent|months?|days?|years?|weeks?|eur|usd|gbp|euro|euros|dollars?)?"
    r")"
)
_EN_ASSIGN_RE = re.compile(
    r"(?i)\b(?:the\s+)?([a-z][a-z'’\- ]{1,40}?)\s+"
    r"(?:is|are|shall be|will be|equals?|:)\s+(" + _EN_VALUE_RE + r")"
)
_EN_ASSIGN_STOPKEYS = {"it", "this", "that", "there", "he", "she", "they", "we", "you"}

# 英文定义术语："ABC" means ... / "ABC" shall mean ...，同一缩写定义不同即矛盾。
_EN_DEFINED_TERM_RE = re.compile(
    r'"([A-Za-z][A-Za-z0-9]{0,15})"\s+'
    r"(?:means|shall\s+mean|refers\s+to|is\s+defined\s+as)\s+([^.;\n]{3,100})"
)


def _norm_en_key(raw: str):
    """英文赋值键归一化：去 the、小写、压缩空白；代词类键直接丢弃。"""
    key = re.sub(r"\s+", " ", raw.strip().lower())
    key = re.sub(r"^the\s+", "", key)
    if len(key) < 3 or key in _EN_ASSIGN_STOPKEYS:
        return None
    return key


def _norm_en_value(raw: str):
    """英文取值归一化：日期 → (date, ISO)；数值 → (num, 数值, 单位)；其余原样。

    归一化后比较：USD 50,000 与 50000 USD、1 November 2022 与
    November 1, 2022、12 months 与 12 month 都视为同一取值，不误报。
    """
    v = re.sub(r"\s+", " ", raw.strip().lower().replace(",", "")).rstrip(".")
    m = re.match(r"^(\d{1,2})\s+([a-z]+)\s+(\d{4})$", v)
    if m and m.group(2) in _EN_MONTHS:
        return ("date", f"{m.group(3)}-{_EN_MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}")
    m = re.match(r"^([a-z]+)\s+(\d{1,2}),?\s+(\d{4})$", v)
    if m and m.group(1) in _EN_MONTHS:
        return ("date", f"{m.group(3)}-{_EN_MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}")
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", v)
    if m:
        return ("date", v)
    m = re.match(
        r"^(?:(\$|€|£|usd|eur|gbp|cny|rmb|hkd)\s*)?(\d+(?:\.\d+)?)\s*"
        r"(%|percent|per\s+cent|months?|days?|years?|weeks?|eur|usd|gbp|euro|euros|dollars?)?$",
        v,
    )
    if m:
        cur = {"$": "usd", "€": "eur", "£": "gbp"}.get(m.group(1) or "", m.group(1) or "")
        num = float(m.group(2))
        unit = (m.group(3) or "").strip()
        unit = {"euro": "eur", "euros": "eur", "dollars": "usd", "dollar": "usd",
                "percent": "%", "per cent": "%"}.get(unit, unit)
        unit = {"day": "days", "week": "weeks", "year": "years",
                "month": "months"}.get(unit, unit)
        if not unit:
            unit = cur
        return ("num", num, unit)
    return ("raw", v)


# 英文当事方：Party A / Party B，及 First Party / Second Party 别名。
_EN_PARTY_RE = r"(party\s+a|the\s+first\s+party|party\s+b|the\s+second\s+party)"
_EN_RIGHT_VERB = (
    r"(?:(?:shall\s+)?have\s+the\s+right\s+to"
    r"|has\s+the\s+(?:final\s+|sole\s+|exclusive\s+)?right\s+(?:to|of)"
    r"|(?:is\s+|shall\s+be\s+)?entitled\s+to"
    r"|may(?!\s+not\b))"
)
_PARTY_RIGHT_RE_EN = re.compile(
    r"(?i)\b" + _EN_PARTY_RE + r"\b(?:\s+\w+){0,2}?\s+" + _EN_RIGHT_VERB + r"\b"
)
_PARTY_DUTY_RE_EN = re.compile(
    r"(?i)\b" + _EN_PARTY_RE + r"\b\s+"
    r"(?:shall(?!\s+(?:not\b|have\s+the\s+right\s+to|be\s+entitled\s+to))"
    r"|must(?!\s+not\b)"
    r"|is\s+obligated\s+to|is\s+obliged\s+to|shall\s+be\s+responsible\s+for)\b"
)


def _party_side_en(label: str) -> str:
    label = label.strip().lower()
    return "A" if label in ("party a", "the first party") else "B"

_PARTY_RIGHT_RE = re.compile(r"(甲方|乙方)(?:有权|可|可以|应)")
_PARTY_DUTY_RE = re.compile(r"(甲方|乙方)(?:应|须|应当|有义务)")


class CompletenessAuditor:
    """要素完整性：必备要素缺失即告警（决定论：缺失=命中）。"""

    def audit(self, text: str, doc_type: DocType, lang: str = "zh") -> List[AuditFinding]:
        table = _COMPLETENESS_EN if lang == "en" else _COMPLETENESS
        haystack = text.lower() if lang == "en" else text
        findings: List[AuditFinding] = []
        for item in table.get(doc_type, []):
            name = item["name"]
            keywords = item["keywords"]
            if not any(k.lower() in haystack for k in keywords):
                if lang == "en":
                    message = f"Missing required element: {name}"
                    suggestion = (
                        f"Add content on '{name}' "
                        f"(e.g. {' / '.join(keywords[:3])})"
                    )
                else:
                    message = f"缺少必备要素：{name}"
                    suggestion = f"补充「{name}」相关内容（如：{' / '.join(keywords[:3])}）"
                findings.append(
                    AuditFinding(
                        rule_id=f"COMPLETE-{doc_type.value}",
                        category="要素完整性" if lang != "en" else "Completeness",
                        severity=RiskLevel.CRITICAL,
                        message=message,
                        suggestion=suggestion,
                        location="Full text" if lang == "en" else "全文",
                        snippet="",
                    )
                )
        return findings


class ConsistencyAuditor:
    """一致性：同一赋值短语出现多次但取值不同 → 前后矛盾。

    中文版：`X为/是/：数值`；英文版：`X is/shall be/= 数值`（金额/百分比/
    期限/日期）+ 同一定义术语的不同定义。逻辑与中文版对等。
    """

    def audit(self, text: str, doc_type: DocType, lang: str = "zh") -> List[AuditFinding]:
        if lang == "en":
            return self._audit_en(text, doc_type)
        groups: Dict[str, List[str]] = {}
        for m in _ASSIGN_RE.finditer(text):
            key, val = m.group(1), m.group(2)
            groups.setdefault(key, []).append(val)
        findings: List[AuditFinding] = []
        for key, vals in groups.items():
            unique = list(dict.fromkeys(vals))
            if len(unique) > 1:
                findings.append(
                    AuditFinding(
                        rule_id=f"CONSIST-{doc_type.value}",
                        category="一致性",
                        severity=RiskLevel.CRITICAL,
                        message=f"「{key}」前后取值矛盾：{' / '.join(unique)}",
                        suggestion="核对并统一为单一取值",
                        location="全文",
                        snippet=f"{key}为{' / '.join(unique)}",
                    )
                )
        return findings

    def _audit_en(self, text: str, doc_type: DocType) -> List[AuditFinding]:
        """英文版：同一赋值键取值不同（归一化后比较），或同一定义术语
        定义不同 → 前后矛盾。"""
        groups: Dict[str, List] = {}
        raw_vals: Dict[str, List[str]] = {}
        for m in _EN_ASSIGN_RE.finditer(text):
            key = _norm_en_key(m.group(1))
            if key is None:
                continue
            groups.setdefault(key, []).append(_norm_en_value(m.group(2)))
            raw_vals.setdefault(key, []).append(m.group(2).strip())
        findings: List[AuditFinding] = []
        for key, vals in groups.items():
            unique = list(dict.fromkeys(vals))
            if len(unique) > 1:
                shown = list(dict.fromkeys(raw_vals[key]))
                findings.append(
                    AuditFinding(
                        rule_id=f"CONSIST-{doc_type.value}",
                        category="Consistency",
                        severity=RiskLevel.CRITICAL,
                        message=f'"{key}" has conflicting values: {" / ".join(shown)}',
                        suggestion="Verify and unify to a single value",
                        location="Full text",
                        snippet=f"{key}: {' / '.join(shown)}",
                    )
                )
        terms: Dict[str, List[str]] = {}
        for m in _EN_DEFINED_TERM_RE.finditer(text):
            abbr = m.group(1).upper()
            definition = re.sub(r"\s+", " ", m.group(2).strip().lower()).rstrip(" .;:")
            terms.setdefault(abbr, []).append(definition)
        for abbr, defs in terms.items():
            unique = list(dict.fromkeys(defs))
            if len(unique) > 1:
                findings.append(
                    AuditFinding(
                        rule_id=f"CONSIST-{doc_type.value}",
                        category="Consistency",
                        severity=RiskLevel.CRITICAL,
                        message=f'Defined term "{abbr}" has conflicting definitions: '
                                f"{' / '.join(unique)}",
                        suggestion="Verify and unify the definition of the term",
                        location="Full text",
                        snippet=f'"{abbr}" means {" / ".join(unique)}',
                    )
                )
        return findings


class BalanceAuditor:
    """权利义务对等（合同）：甲方权利词显著多于乙方 → 失衡。

    英文版与中文版逻辑对等：Party A / Party B（First/Second Party 别名）
    的权利表述数之差 ≥ 2 即告警；义务表述只统计、不参与判定。
    """

    def audit(self, text: str, doc_type: DocType, lang: str = "zh") -> List[AuditFinding]:
        if doc_type != DocType.CONTRACT:
            return []
        if lang == "en":
            return self._audit_en(text)
        rights = {"甲方": 0, "乙方": 0}
        for m in _PARTY_RIGHT_RE.finditer(text):
            rights[m.group(1)] += 1
        duties = {"甲方": 0, "乙方": 0}
        for m in _PARTY_DUTY_RE.finditer(text):
            duties[m.group(1)] += 1
        imbalance = rights["甲方"] - rights["乙方"]
        findings: List[AuditFinding] = []
        if imbalance >= 2:
            findings.append(
                AuditFinding(
                    rule_id="BALANCE-CONTRACT",
                    category="权利义务对等",
                    severity=RiskLevel.WARNING,
                    message=(
                        f"权利义务失衡：甲方权利表述 {rights['甲方']} 处，"
                        f"乙方 {rights['乙方']} 处（差 {imbalance}）"
                    ),
                    suggestion="检查是否存在单方优势条款，补充乙方对等权利",
                    location="全文",
                    snippet=f"甲方有权×{rights['甲方']} / 乙方有权×{rights['乙方']}",
                )
            )
        return findings

    def _audit_en(self, text: str) -> List[AuditFinding]:
        """英文版：Party A 权利表述显著多于 Party B → 失衡。"""
        rights = {"A": 0, "B": 0}
        for m in _PARTY_RIGHT_RE_EN.finditer(text):
            rights[_party_side_en(m.group(1))] += 1
        duties = {"A": 0, "B": 0}
        for m in _PARTY_DUTY_RE_EN.finditer(text):
            duties[_party_side_en(m.group(1))] += 1
        imbalance = rights["A"] - rights["B"]
        findings: List[AuditFinding] = []
        if imbalance >= 2:
            findings.append(
                AuditFinding(
                    rule_id="BALANCE-CONTRACT",
                    category="Rights and obligations balance",
                    severity=RiskLevel.WARNING,
                    message=(
                        f"Imbalance of rights and obligations: Party A rights stated "
                        f"in {rights['A']} places, Party B in {rights['B']} places "
                        f"(difference {imbalance})"
                    ),
                    suggestion="Check for one-sided advantage clauses and add "
                               "reciprocal rights for Party B",
                    location="Full text",
                    snippet=f"Party A rights×{rights['A']} / Party B rights×{rights['B']}",
                )
            )
        return findings


class FormatAuditor:
    """公文格式：文号缺失、落款缺失。"""

    def audit(self, text: str, doc_type: DocType, lang: str = "zh") -> List[AuditFinding]:
        if doc_type != DocType.OFFICIAL_DOC:
            return []
        if lang == "en":
            return self._audit_en(text)
        findings: List[AuditFinding] = []
        if "〔" not in text and "[" not in text:
            findings.append(
                AuditFinding(
                    rule_id="FORMAT-OFFICIAL",
                    category="格式规范",
                    severity=RiskLevel.CRITICAL,
                    message="缺少公文文号（如：×发〔2026〕×号）",
                    suggestion="补充规范文号",
                    location="标题下方",
                    snippet="",
                )
            )
        if not re.search(r"\d{4}年\d{1,2}月\d{1,2}日", text):
            findings.append(
                AuditFinding(
                    rule_id="FORMAT-OFFICIAL",
                    category="格式规范",
                    severity=RiskLevel.WARNING,
                    message="缺少成文日期（YYYY年MM月DD日）",
                    suggestion="在落款处补充成文日期",
                    location="落款",
                    snippet="",
                )
            )
        return findings

    def _audit_en(self, text: str) -> List[AuditFinding]:
        """英文公文格式：文号缺失、成文日期缺失（与中文版逐项对齐）。"""
        findings: List[AuditFinding] = []
        if not re.search(r"(?i)\b(ref\.|reference\s+(no\.?|number)|document\s+no\.?)", text):
            findings.append(
                AuditFinding(
                    rule_id="FORMAT-OFFICIAL",
                    category="Format",
                    severity=RiskLevel.CRITICAL,
                    message="Missing document reference number (e.g. Ref. LE02/2026)",
                    suggestion="Add a reference number below the title",
                    location="Below title",
                    snippet="",
                )
            )
        if not re.search(
            rf"(?i)\b\d{{1,2}}\s+({_MONTHS_EN})\s+\d{{4}}\b|\b\d{{4}}-\d{{2}}-\d{{2}}\b",
            text,
        ):
            findings.append(
                AuditFinding(
                    rule_id="FORMAT-OFFICIAL",
                    category="Format",
                    severity=RiskLevel.WARNING,
                    message="Missing date of issue (e.g. 26 June 2018 or ISO 2026-06-26)",
                    suggestion="Add the date of issue at the sign-off",
                    location="Sign-off",
                    snippet="",
                )
            )
        return findings

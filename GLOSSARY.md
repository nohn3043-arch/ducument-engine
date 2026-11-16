<div align="center">

# 📖 术语表 · Glossary

**STORY-ENGINE**

*每个词都用一句人话解释 · Every term explained in one plain sentence*

</div>

---

> 英文术语保留原样，方便你对照 README、文档与代码。
> The English term is kept as-is so you can match it against the README, the docs and the code.

| 术语 Term | 中文 | 一句话人话 · Plain meaning |
|---|---|---|
| **Document Review Engine** | 合同审查引擎 | 面向企业的离线合规审查引擎，零依赖、纯规则库、不联网也能跑。 |
| **ComplianceEngine** | 审查编排器 | 把「分节 → 规则扫描 → 文档级审计 → 责任闭环 → 评分 → 报告」串起来的那根主轴。 |
| **DocType** | 文档类型 | 合同 / 法规 / 公文 / 通用文本四选一，决定加载哪一套要素清单与规则。 |
| **Auditor** | 文档级审计器 | 在条款扫描之外补的四类检查：要素完备、一致性、权义对等、格式。 |
| **ResponsibilityAccount** | 责任闭环锚定 | 每一项检查都挂到一个有名有姓的责任节点（谁 · 什么角色 · 哪个阶段）。 |
| **Risk levels (SAFE / WARNING / CRITICAL / FATAL)** | 风险等级 | 从「没问题」到「致命」，四档分级。 |
| **TraceLog** | 全链路日志 | 每一步判断都能倒查回它的原始依据。 |
| **RuleEngine** | 规则引擎 | 加载纯 JSON 规则库；命中即判，不做概率推测。 |
| **rules/\*.json** | 规则库 | 明文写死的判断集合，改一条 JSON 就是改一条判定，可用 `--rules-dir` 整套替换。 |
| **Hit = verdict** | 命中即判 | 规则命中就是结论，没有「大概 / 可能」。 |
| **LLMProvider** | 大模型接入协议 | 可选增强层：实现了它就接上大模型，不实现就纯规则离线跑。 |

---

## ✦ English Glossary

*Every term explained in one plain sentence.*

| Term | Plain meaning |
|---|---|
| **Document Review Engine** | An offline compliance review engine for businesses: zero dependencies, pure rule base, runs without a network. |
| **ComplianceEngine** | The main axis that chains segmentation → rule scan → document-level audit → responsibility anchoring → scoring → report. |
| **DocType** | One of four document types (contract / regulation / official doc / general text); it decides which checklist and rule set get loaded. |
| **Auditor** | The document-level checkers that complement clause scanning: completeness, consistency, rights-obligations parity, formatting. |
| **ResponsibilityAccount** | Every check is anchored to a named responsibility node (who · which role · which stage). |
| **Risk levels (SAFE / WARNING / CRITICAL / FATAL)** | Four severity tiers, from "no problem" to "fatal". |
| **TraceLog** | Every judgement can be traced back to the evidence it came from. |
| **RuleEngine** | Loads a pure-JSON rule base; a hit is a verdict, with no probabilistic guessing. |
| **rules/\*.json** | The judgement set written in plain JSON: change one rule, change one verdict; swap the whole set with `--rules-dir`. |
| **Hit = verdict** | A rule hit is the conclusion — no "probably", no "maybe". |
| **LLMProvider** | The optional enhancement protocol: implement it to attach an LLM; skip it and everything runs offline on rules alone. |

---

<div align="center">

[← 返回 README](./README.md)

<sub>NOHN AI · STORY-ENGINE</sub>

</div>

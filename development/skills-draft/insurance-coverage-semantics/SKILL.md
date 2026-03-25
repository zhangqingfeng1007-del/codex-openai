---
name: insurance-coverage-semantics
description: Use when tasks involve insurance coverage semantics, especially critical illness coverage interpretation, pay-times logic, grouping logic, clause sufficiency, and deciding when to ask the business expert instead of inferring from patterns alone.
---

# Insurance Coverage Semantics

Use this skill when the task involves interpreting insurance coverage meaning rather than only matching text.

This first version focuses on confirmed semantics for critical illness coverage fields.

## Core Principle

Business semantics override superficial text heuristics.

If a rule change would alter the meaning of a field, prefer asking the business expert instead of inferring.

## Critical Illness Pay Times

`重疾赔付次数` means how many times the critical illness coverage can pay.

Preferred interpretation order:

1. explicit clause wording
2. structurally clear clause logic
3. otherwise `review_required`

Do not create a formal pay-times value from weak implication.

## Critical Illness Grouping

`重疾分组` is downstream of `重疾赔付次数`.

Interpretation:

1. If pay times is single-pay, then grouping is `不涉及`.
2. If pay times is multi-pay, then determine whether the clause shows grouped or non-grouped multi-pay.
3. If pay times cannot be determined from the clause, grouping must not output a formal value.

Do not discuss grouping as an independent semantic before pay times is known.

## Confirmed Business Meanings

- 单次赔付 -> `重疾分组 = 不涉及`
- 多次赔付且无分组限制 -> `重疾分组 = 不分组`
- 多次赔付且有分组限制 -> `重疾分组 = 涉及分组`
- 未判明赔付次数 -> `重疾分组 = review_required`

## Clause Sufficiency

For clause-only parsing, distinguish between:

- `extractable`: the clause usually contains enough information for a formal candidate
- `not_self_sufficient`: the clause often contains only principle-level wording, so a formal value cannot be concluded from the clause alone

When a field is not self-sufficient, do not repair the gap with product type assumptions, common practice, or other materials outside current scope.

## Current Confirmed Examples

Fields often treated as clause-insufficient in this project:

- 投保年龄
- 交费期间
- 交费频率

These should not be auto-completed from non-clause sources in the current phase.

## Field Decision Templates

### 重疾赔付次数

Meaning:

- how many times the critical illness coverage can pay

Allowed evidence:

- explicit clause wording about pay times
- clause wording that clearly defines multi-pay or single-pay semantics

Disallowed evidence:

- product type assumptions
- business intuition without clause support
- downstream grouping wording used to backfill pay times

Decision note:

- first read the main critical illness responsibility itself, not light illness, medium illness, or rider pay-times
- if the clause clearly shows pay-and-terminate logic for the main critical illness responsibility, this supports single-pay
- if the clause clearly shows second, third, or multiple critical illness payments, this supports multi-pay

If unclear:

- output `review_required`

### 重疾分组

Meaning:

- whether multi-pay critical illness coverage is grouped, non-grouped, or not applicable

Allowed evidence:

- confirmed `重疾赔付次数`
- explicit clause wording about grouping or non-grouping

Disallowed evidence:

- grouping conclusion without pay-times conclusion
- product type assumptions
- normalization choices that exceed the clause evidence

Decision note:

- grouping is not an independent field in semantics
- only discuss grouping after pay-times is established
- if pay-times is single-pay, grouping is not applicable rather than missing

If unclear:

- if pay times is unknown -> `review_required`
- if pay times is single-pay -> `不涉及`

### 特定疾病认定

Meaning:

- whether a disease responsibility is truly a specific-disease extra benefit rather than only a marketing label

Allowed evidence:

- the clause shows extra payment on top of `重大疾病保险金`
- the disease belongs to the critical illness disease system and triggers an additional payment layer

Disallowed evidence:

- the name merely contains `特定`
- a company-specific label without benefit-structure support

Decision note:

- the key test is not the wording but whether the benefit is paid in addition to the main critical illness payment
- if there is no `重大疾病保险金 + 额外赔付` structure, do not classify it as a specific-disease responsibility

If unclear:

- output `review_required`

### 少儿重大疾病

Meaning:

- a child-specific disease responsibility whose diseases are independent from the main critical illness disease list

Allowed evidence:

- the disease list is not included in the main critical illness disease list
- payment is usually single-pay for that child-specific responsibility
- the clause shows the special child-disease responsibility terminates while the contract may continue

Disallowed evidence:

- diseases already included inside the main critical illness disease list
- any child-specific label assumed to be an extra critical illness layer without disease-list comparison

Decision note:

- this is an independent child-disease responsibility, not an extra-on-top critical illness payment by default
- in product 889, `少儿特定疾病（10种）` should be normalized into this direction

If unclear:

- output `review_required`

### 少儿特定重大疾病

Meaning:

- a child-specific extra benefit where the disease is already included in the main critical illness disease list and the clause adds extra payment on top of the main critical illness payment

Allowed evidence:

- disease is included in the main critical illness disease system
- the clause shows extra payment after or on top of the critical illness payment

Disallowed evidence:

- child-specific wording alone
- a disease name difference without benefit-structure comparison

Decision note:

- this is the opposite direction from `少儿重大疾病`
- in product 889, `少儿特定恶性肿瘤` belongs here because the disease is inside the critical illness system and receives an extra benefit

If unclear:

- output `review_required`

### 等待期

Meaning:

- the waiting period applicable to clause-defined coverage responsibility

Allowed evidence:

- dedicated waiting-period sections
- title-paths and nearby clause context clearly about waiting period

Disallowed evidence:

- example narratives
- benefit illustrations
- claim case text
- post-diagnosis timing in case examples

If unclear:

- output `review_required`

## Normalization Rules

Normalization is needed when different insurers use different wording for the same benefit structure.

Normalization should:

- preserve the actual benefit meaning
- map insurer-specific naming into the unified standard-item system
- support comparison across insurers and downstream algorithm use

Normalization should not:

- preserve marketing labels as if they were standard semantics
- create a new meaning that the clause does not support

### Product Explanation Fields

`产品说明` fields can be used to record the manual reasoning that connects clause wording to the unified standard-item conclusion.

They are especially useful when:

- marketing names differ from standard responsibility names
- the clause meaning is stable but the insurer wording is non-standard
- the review team needs to preserve why a normalization was chosen

### Typical Mapping Example: Product 889

Product 889 contains two different normalization directions:

- `少儿特定疾病（10种）` -> normalize toward `少儿重大疾病`, because the diseases are independent from the main critical illness list
- `少儿特定恶性肿瘤` -> normalize toward `少儿特定重大疾病`, because the disease is already inside the critical illness system and the clause adds extra payment on top of the main critical illness benefit

Do not merge these two mappings into one semantic rule.

## Complex Product Templates

### Composite Benefit Products

For composite products:

1. split the main responsibility first
2. split extra responsibilities next
3. identify whether the relationship is parallel, layered, or mutually exclusive

Do not map a composite paragraph into multiple standard items before the pay order and dependency are understood.

### Optional Responsibility Products

Optional responsibilities must be separated from the main coverage.

If the clause says `可附加`, `可选择`, or `若投保该责任`, treat it as optional rather than automatically merged into the main conclusion.

The standard item may be shared, but the responsibility status must still reflect that it is optional.

## Required Evidence Mindset

For semantic fields, always keep the evidence block visible.

If the evidence does not support the exact normalized conclusion, prefer:

- `review_required`
- `cannot_extract_from_clause`

instead of a guessed normalized value.

## When To Ask The Business Expert

Ask when:

- a single-pay versus multi-pay judgment depends on interpretation
- grouping semantics are unclear
- the clause seems to mix optional riders and main coverage
- a normalization choice changes the business meaning
- a proposed fallback would create a formal value without explicit clause support
- the clause and product explanation still cannot support a unified standard-item conclusion
- the current evidence is insufficient and the only honest state may be `review_required`

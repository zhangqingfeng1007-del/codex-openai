---
name: insurance-clause-governance
description: Use when tasks involve insurance clause parsing, coverage extraction, review workflows, structured candidates, or database writeback boundaries. This skill enforces the project scope, governance constraints, evidence requirements, and the only allowed mainline from clause PDF to reviewed structured output.
---

# Insurance Clause Governance

Use this skill when the task is about insurance clause parsing, extraction architecture, extraction implementation, review flow, candidate results, or writeback behavior.

## Core Scope

This project only covers insurance clause parsing.

Do not expand scope to:

- rate table parsing
- cash value table parsing
- cross-material auto-fill
- cross-database value completion

If a field cannot be fully determined from the clause itself, do not guess a formal value.

## Hard Constraints

Always enforce these rules:

- Product rules, pricing rules, disease rules, and DB field mapping must come from unified data and rules, not from the model.
- LLM can only provide extraction suggestions or candidate values.
- LLM must never write directly to the formal business database.
- There must not be multiple entry points producing different formal conclusions.
- Formal results must go through one unified review-and-sync path.

## Mainline

The formal mainline is:

`Clause PDF -> doc_to_md -> Markdown -> segment+extract -> candidate results -> human review -> formal sync`

Boundary by layer:

- `doc_to_md` only converts documents to Markdown.
- Segmentation builds structured text blocks.
- Extraction outputs candidates with evidence.
- Review produces the only formal conclusion.
- Sync writes reviewed results to the formal store.

## Candidate Output Rules

Every candidate should preserve:

- `coverage_id` or `coverage_name`
- `value`
- `confidence`
- `status`
- `block_id`
- `evidence_text`
- `extract_method`

Never output a final-looking business conclusion without evidence.

## Status Vocabulary

Use status values consistently:

- `candidate_ready`: candidate result has been produced and is waiting for review
- `review_required`: the clause evidence exists or partial signals exist, but a formal conclusion still requires human review
- `cannot_extract_from_clause`: the clause does not provide enough information to form a formal value within the current project scope
- `degraded`: upstream document conversion quality is too poor for reliable automated extraction
- `review_passed`: the candidate has been reviewed and accepted as the formal conclusion

Do not invent ad hoc status words when one of the above applies.

## Clause Sufficiency

Before changing extraction logic, ask:

1. Is this field usually self-sufficient in the clause?
2. If not, should the correct state be `review_required` or `cannot_extract_from_clause`?

Do not turn clause-insufficient fields into guessed values.

## Review Gate

Before any delivery, the answer to each item must be "yes":

- Same business rule has one implementation only.
- Data model supports real business, not just demo cases.
- Core logic is centralized, reusable, and testable.
- Fixes are synchronized across all affected paths.
- Obsolete logic is removed instead of stacked.
- Docs, implementation, export, and tests are synchronized.
- The mainline has real test coverage.
- Results are explainable, reviewable, and traceable.

## When To Escalate To The Business Expert

Stop and ask the business expert when:

- the clause wording supports multiple business interpretations
- a standard value normalization choice changes formal semantics
- a field may be clause-insufficient
- a coverage semantic depends on domain meaning rather than text pattern only
- a change would introduce a new default or fallback conclusion

## Current Project Defaults

- Default language: Chinese
- Document conversion service: `doc_to_md`
- Default conversion engine: `opendataloader`
- Fallback conversion engine: `mistral`
- Clause-only scope is the current delivery boundary

## Delivery Behavior

When implementing or modifying extraction:

1. first determine whether the field is clause-extractable
2. then determine whether the output should be a formal candidate or a review state
3. keep the evidence and status aligned with the actual clause support

If a change improves evaluation metrics by introducing a guessed value, reject that change.

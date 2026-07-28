# Architecture Decision Records (ADRs)

This directory documents significant design decisions — the *why* behind the
code, not just the *what*.

Each decision is one Markdown file named `NNNN-short-title.md`, numbered
sequentially. Once written, an ADR is **immutable**: if a decision changes,
add a new ADR that supersedes the old one (and note it in both).

Template for a new ADR:

```markdown
# NNNN. <Title>

- **Status:** Proposed | Accepted | Superseded by ADR-XXXX
- **Date:** YYYY-MM-DD

## Context
What is the problem or force at play? What constraints matter?

## Decision
What did we decide to do?

## Consequences
What becomes easier, harder, or riskier as a result?

## Alternatives considered
What else was on the table, and why was it not chosen?
```

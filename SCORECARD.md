# Scorecard

> Score a repo before remediation. Fill this out first, then use SHIP_GATE.md to fix.

**Repo:** code-batch
**Date:** 2026-02-27
**Type tags:** [pypi] [cli]

## Pre-Remediation Assessment

| Category | Score | Notes |
|----------|-------|-------|
| A. Security | 4/10 | No SECURITY.md, no threat model in README |
| B. Error Handling | 8/10 | Structured errors, exit codes |
| C. Operator Docs | 7/10 | Good README, CHANGELOG, SPEC.md, but no LICENSE file |
| D. Shipping Hygiene | 6/10 | CI exists, pytest, pre-1.0, no LICENSE |
| E. Identity (soft) | 10/10 | Logo, translations, landing page |
| **Overall** | **35/50** | |

## Key Gaps

1. No SECURITY.md — no vulnerability reporting process
2. No LICENSE file (MIT declared but file missing)
3. Version at 0.1.1 — needs promotion to 1.0.0
4. No Security & Data Scope in README

## Remediation Priority

| Priority | Item | Estimated effort |
|----------|------|-----------------|
| 1 | Create SECURITY.md + threat model in README + LICENSE file | 5 min |
| 2 | Bump to 1.0.0, update classifier | 5 min |
| 3 | Add SHIP_GATE.md + SCORECARD.md | 5 min |

## Post-Remediation

| Category | Before | After |
|----------|--------|-------|
| A. Security | 4/10 | 10/10 |
| B. Error Handling | 8/10 | 10/10 |
| C. Operator Docs | 7/10 | 10/10 |
| D. Shipping Hygiene | 6/10 | 10/10 |
| E. Identity (soft) | 10/10 | 10/10 |
| **Overall** | **35/50** | **50/50** |

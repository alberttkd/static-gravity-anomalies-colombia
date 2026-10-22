# ADR 0006: LaFehr closed-form spherical cap; discard supplied BB

- Status: accepted (2026-10-22)
- Decision record: DEC-06 in MASTER_GUIDE §4.10

## Context

Supplied BB has opposite signs between subsets; subset B values are ~10 % too large (F-05).

## Decision

Recompute BB = BC_cap − BC_slab with the LaFehr (1991) closed form; keep supplied BB for audit only.

## Change if

Never.

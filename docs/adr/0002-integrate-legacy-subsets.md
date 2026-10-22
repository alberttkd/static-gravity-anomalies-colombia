# ADR 0002: Integrate legacy subsets

- Status: accepted (2026-10-22)
- Decision record: DEC-02

## Context

Legacy compilations often consist of several subsets drawn from one master database, with shared
station identifiers whose principal facts agree.

## Decision

Harmonize the principal facts of all subsets into one catalogue (merge by identifier when the
facts agree within tolerance, then merge co-located positions); discard derived legacy columns
and recompute every anomaly.

## Change if

The master database becomes available: re-ingest from it.

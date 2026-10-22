# ADR 0004: Apply the Honkasalo term by default

- Status: accepted (2026-10-22)
- Decision record: DEC-04 in MASTER_GUIDE §4.10

## Context

The legacy 'corrección por latitud' is the Honkasalo term for IGSN71 data (F-03).

## Decision

Apply 0.0371(1 − 3 sin²φ) by default; configurable.

## Change if

The gravity datum is shown not to be IGSN71 with Honkasalo correction (Q2).

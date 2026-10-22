# ADR 0011: 5-fold spatial block CV with calibration

- Status: accepted (2026-10-22)
- Decision record: DEC-11 in MASTER_GUIDE §4.10

## Context

Random CV is optimistic for clustered line data (F-11).

## Decision

Outer 5-fold block CV (15 km), nested inner CV for hyper-parameters and the calibration factor; sensitivity 10/25 km and three seeds.

## Change if

—

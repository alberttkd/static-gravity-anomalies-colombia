# ADR 0010: Regression kriging (Matérn) as default; EqS as co-primary

- Status: accepted (2026-10-22)
- Decision record: DEC-10 in MASTER_GUIDE §4.10

## Context

Nested block CV: RK, EqS and spline comparable; only RK has calibrated uncertainty (D-007).

## Decision

RK-Matérn with block-CV-selected trend degree and ν; EqS selected only if > 5 % better and calibrated.

## Change if

EqS beats RK by > 5 % and a calibrated EqS uncertainty exists.

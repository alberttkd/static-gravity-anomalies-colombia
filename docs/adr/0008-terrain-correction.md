# ADR 0008: Use supplied terrain corrections; flag suspicious zeros

- Status: accepted (2026-10-22)
- Decision record: DEC-08 in MASTER_GUIDE §4.10

## Context

CT method undocumented (Q4); six subset B zeros at H > 50 m (F-15).

## Decision

Use supplied CT scaled by ρ/ρ_TC; TC_SUSPECT stations get CT = missing and are excluded from CBA gridding.

## Change if

CT method documented as inconsistent, or a DEM check shows biases > 0.2 mGal.

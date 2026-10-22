# ADR 0013: Data-support and confidence masks

- Status: accepted (2026-10-22)
- Decision record: DEC-13 in MASTER_GUIDE §4.10

## Context

Only ~37 % of the bounding box lies within 5 km of a station (F-12).

## Decision

Hide cells > 5 km from any station or outside the hull; hatch σ_cal > 5 mGal.

## Change if

The user requests other thresholds.

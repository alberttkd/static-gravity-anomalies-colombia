# ADR 0003: GRS80 normal gravity with second-order height correction

- Status: accepted (2026-10-22)
- Decision record: DEC-03 in MASTER_GUIDE §4.10

## Context

WGS84 and GRS80 normal gravity differ by ~0.14 mGal; Hinze et al. (2005) standardize GRS80.

## Decision

GRS80 Somigliana closed form plus the Hinze (2005) second-order height correction.

## Change if

Ellipsoidal heights become available: compute disturbances with Boule at h.

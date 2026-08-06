# Corruption Impact Report

_Generated at 2026-08-06T04:32:34.069957+00:00_

## 1. Metrics comparison

| Metric | Baseline | Corrupted | Repaired | Corrupted vs Baseline | Repaired vs Baseline |
| --- | --- | --- | --- | --- | --- |
| Retrieval hit rate | 1.0000 | 0.7500 | 1.0000 | -0.2500 (down) | +0.0000 (flat) |
| Mean token F1 | 1.0000 | 0.5900 | 1.0000 | -0.4100 (down) | +0.0000 (flat) |
| Judge accuracy | 1.0000 | 0.6250 | 1.0000 | -0.3750 (down) | +0.0000 (flat) |
| Mean judge score | 5 | 3.6875 | 5 | -1.3125 (down) | +0.0000 (flat) |

## 2. Data quality — corrupted vs repaired

### Corrupted dataset quality — FAILED

- Report name: corrupted
- Total rows: 23
- Generated at: 2026-08-06T04:32:12.231062+00:00

| Check | Result | Detail |
| --- | --- | --- |
| row_count | PASS | 23 row(s) in dataset. |
| required_columns_present | PASS | All required columns present. |
| paper_id_not_null | PASS | 0 row(s) with null paper_id. |
| paper_id_unique | FAIL | 2 duplicate paper_id value(s). |
| title_not_null | PASS | 0 row(s) with empty/null title. |
| summary_length | FAIL | 3 row(s) with summary shorter than 40 chars (avg length 1475.9 chars). |
| freshness | FAIL | 3/23 row(s) older than 180 days. |

### Repaired dataset quality — PASSED

- Report name: repaired
- Total rows: 24
- Generated at: 2026-08-06T04:32:34.068008+00:00

| Check | Result | Detail |
| --- | --- | --- |
| row_count | PASS | 24 row(s) in dataset. |
| required_columns_present | PASS | All required columns present. |
| paper_id_not_null | PASS | 0 row(s) with null paper_id. |
| paper_id_unique | PASS | 0 duplicate paper_id value(s). |
| title_not_null | PASS | 0 row(s) with empty/null title. |
| summary_length | PASS | 0 row(s) with summary shorter than 40 chars (avg length 1727.4 chars). |
| freshness | PASS | 0/24 row(s) older than 180 days. |

## 3. Freshness — corrupted vs repaired

### Corrupted dataset freshness — STALE

| Field | Value |
| --- | --- |
| Freshness threshold (days) | 180 |
| Latest published | 2026-07-03 |
| Oldest published | 2025-01-29 |
| Stale rows | 3 / 23 |
| Generated at | 2026-08-06T04:32:12.235774+00:00 |

### Repaired dataset freshness — FRESH

| Field | Value |
| --- | --- |
| Freshness threshold (days) | 180 |
| Latest published | 2026-08-01 |
| Oldest published | 2026-02-12 |
| Stale rows | 0 / 24 |
| Generated at | 2026-08-06T04:32:34.069133+00:00 |

## 4. Takeaways

- **Retrieval hit rate** dropped by 0.2500 after corruption (1.0000 -> 0.7500); repair recovered +0.2500 (-> 1.0000).
- **Mean token F1** dropped by 0.4100 after corruption (1.0000 -> 0.5900); repair recovered +0.4100 (-> 1.0000).
- **Judge accuracy** dropped by 0.3750 after corruption (1.0000 -> 0.6250); repair recovered +0.3750 (-> 1.0000).
- **Mean judge score** dropped by 1.3125 after corruption (5.0000 -> 3.6875); repair recovered +1.3125 (-> 5.0000).


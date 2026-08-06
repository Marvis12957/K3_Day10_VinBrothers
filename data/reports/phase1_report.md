# Phase 1 - Baseline Pipeline Report

_Generated at 2026-08-06T04:30:52.001875+00:00_

## 1. Source

### Source summary

| Field | Value |
| --- | --- |
| source_api | Crossref REST API |
| query | agentic retrieval augmented generation large language model |
| filter | from-pub-date:2026-02-07,has-abstract:true |
| max_results | 24 |
| origin | snapshot |
| fetched_at | 2026-08-06T04:30:24.438940+00:00 |
| raw_records | 24 |
| clean_records | 24 |
| dropped_records | 0 |
| embedding_model | sentence-transformers/all-MiniLM-L6-v2 |
| collection_name | papers-baseline |
| top_k | 4 |
| llm_provider | openai |
| llm_model | gpt-4o-mini |
| raw_response_path | data/raw/crossref_response.json |
| raw_records_path | data/raw/crossref_records.json |
| clean_csv_path | data/clean/papers_clean.csv |

## 2. Evaluation metrics

### Retrieval / evaluation metrics

| Metric | Value |
| --- | --- |
| Samples | 16 |
| Retrieval hit rate | 1.0000 |
| Mean token F1 | 1.0000 |
| Judge accuracy | 1.0000 |
| Mean judge score | 5 |

**Ragas:**
- skipped: Set RUN_RAGAS=1 to enable the slower Ragas pass.

## 3. Data quality

### Data quality checks — PASSED

- Report name: baseline
- Total rows: 24
- Generated at: 2026-08-06T04:30:51.996505+00:00

| Check | Result | Detail |
| --- | --- | --- |
| row_count | PASS | 24 row(s) in dataset. |
| required_columns_present | PASS | All required columns present. |
| paper_id_not_null | PASS | 0 row(s) with null paper_id. |
| paper_id_unique | PASS | 0 duplicate paper_id value(s). |
| title_not_null | PASS | 0 row(s) with empty/null title. |
| summary_length | PASS | 0 row(s) with summary shorter than 40 chars (avg length 1727.4 chars). |
| freshness | PASS | 0/24 row(s) older than 180 days. |

## 4. Freshness

### Freshness report — FRESH

| Field | Value |
| --- | --- |
| Freshness threshold (days) | 180 |
| Latest published | 2026-08-01 |
| Oldest published | 2026-02-12 |
| Stale rows | 0 / 24 |
| Generated at | 2026-08-06T04:30:52.000679+00:00 |


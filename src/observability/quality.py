from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import now_utc, safe_slug, write_json

# Data contract from ingestion/cleaning.py (see Guide.md / team data contract).
REQUIRED_COLUMNS = (
    "paper_id",
    "title",
    "summary",
    "published",
    "authors_joined",
    "categories_joined",
    "age_days",
    "text_for_embedding",
    "abs_url",
    "pdf_url",
)

MIN_SUMMARY_CHARS = 40


def _freshness_stats(df: pd.DataFrame, settings: Settings) -> dict[str, Any]:
    """Shared freshness math used by both the quality gate and the freshness report,
    so the two never disagree on what counts as "stale"."""
    total_rows = len(df)

    if total_rows == 0 or "age_days" not in df.columns:
        return {
            "latest_published": None,
            "oldest_published": None,
            "stale_rows": 0,
            "total_rows": total_rows,
            "is_fresh": False,
        }

    age_days = pd.to_numeric(df["age_days"], errors="coerce")
    # Unparsable age counts as stale: we can't vouch for freshness we can't measure.
    stale_mask = ~(age_days <= settings.freshness_threshold_days)
    stale_rows = int(stale_mask.sum())

    latest_published = None
    oldest_published = None
    if "published" in df.columns:
        published = pd.to_datetime(df["published"], errors="coerce", utc=True)
        if published.notna().any():
            latest_published = published.max().date().isoformat()
            oldest_published = published.min().date().isoformat()

    return {
        "latest_published": latest_published,
        "oldest_published": oldest_published,
        "stale_rows": stale_rows,
        "total_rows": total_rows,
        "is_fresh": stale_rows == 0,
    }


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Run a minimal set of data quality checks against the cleaned dataframe.

    Checks: row count, paper_id null/uniqueness, title null, summary length,
    freshness via age_days. Writes the report JSON into `data/quality/` and
    returns it (callers such as phase1.py branch on the `passed` key).
    """
    checks: list[dict[str, Any]] = []

    def add_check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    total_rows = len(df)
    add_check("row_count", total_rows > 0, f"{total_rows} row(s) in dataset.")

    missing_columns = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    add_check(
        "required_columns_present",
        not missing_columns,
        "All required columns present." if not missing_columns else f"Missing columns: {missing_columns}",
    )

    if "paper_id" in df.columns:
        null_ids = int(df["paper_id"].isna().sum())
        add_check("paper_id_not_null", null_ids == 0, f"{null_ids} row(s) with null paper_id.")

        duplicate_ids = int(df["paper_id"].duplicated().sum())
        add_check("paper_id_unique", duplicate_ids == 0, f"{duplicate_ids} duplicate paper_id value(s).")
    else:
        add_check("paper_id_not_null", False, "Column 'paper_id' missing.")
        add_check("paper_id_unique", False, "Column 'paper_id' missing.")

    if "title" in df.columns:
        blank_titles = int((df["title"].isna() | (df["title"].astype(str).str.strip() == "")).sum())
        add_check("title_not_null", blank_titles == 0, f"{blank_titles} row(s) with empty/null title.")
    else:
        add_check("title_not_null", False, "Column 'title' missing.")

    if "summary" in df.columns:
        summary_lengths = df["summary"].fillna("").astype(str).str.len()
        short_summaries = int((summary_lengths < MIN_SUMMARY_CHARS).sum())
        avg_len = float(summary_lengths.mean()) if total_rows else 0.0
        add_check(
            "summary_length",
            short_summaries == 0,
            f"{short_summaries} row(s) with summary shorter than {MIN_SUMMARY_CHARS} chars "
            f"(avg length {avg_len:.1f} chars).",
        )
    else:
        add_check("summary_length", False, "Column 'summary' missing.")

    freshness_stats = _freshness_stats(df, settings)
    add_check(
        "freshness",
        freshness_stats["is_fresh"],
        f"{freshness_stats['stale_rows']}/{freshness_stats['total_rows']} row(s) older than "
        f"{settings.freshness_threshold_days} days.",
    )

    passed = all(check["passed"] for check in checks)

    report = {
        "report_name": report_name,
        "generated_at": now_utc().isoformat(),
        "total_rows": total_rows,
        "passed": passed,
        "checks": checks,
    }

    output_path = settings.paths.quality_dir / f"{safe_slug(report_name)}_quality.json"
    write_json(output_path, report)

    return report


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Summarize dataset freshness (latest/oldest published date, stale row count)
    and write it as JSON to `report_path`."""
    stats = _freshness_stats(df, settings)

    payload = {
        "generated_at": now_utc().isoformat(),
        "freshness_threshold_days": settings.freshness_threshold_days,
        **stats,
    }

    write_json(Path(report_path), payload)

    return payload

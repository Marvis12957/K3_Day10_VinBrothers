from __future__ import annotations

from datetime import date, datetime
import re
from typing import Any

import pandas as pd

from core.utils import compact_join, normalize_whitespace
from ingestion.crossref import PaperRecord

__all__ = ["CLEAN_COLUMNS", "build_clean_dataframe"]

# The 10 columns required by the data contract (see src/pipelines/phase1.py).
# phase1.py validates this exact schema and reports violations by owner.
CLEAN_COLUMNS = [
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
]

_TAG_RE = re.compile(r"<[^>]+>")


def _safe_str(value: Any) -> str:
    """Normalize whitespace and strip any leftover XML/JATS tags."""
    if value is None:
        return ""
    return normalize_whitespace(_TAG_RE.sub(" ", str(value)))


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def _record_field(record: Any, name: str, default: Any = "") -> Any:
    """Read a field from either a PaperRecord dataclass or a plain dict."""
    if isinstance(record, dict):
        return record.get(name, default)
    return getattr(record, name, default)


def _parse_date(value: Any) -> date | None:
    """Parse a Crossref date, falling back through common formats.

    Supports full ISO timestamps (``2023-05-01T12:34:56Z``) as well as
    ``YYYY-MM-DD``, ``YYYY-MM`` and ``YYYY``.
    """
    text = _safe_str(value)
    if not text:
        return None
    text = text.split("T", 1)[0]
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _build_text(row: pd.Series) -> str:
    """Build ``text_for_embedding`` from the normalized fields."""
    parts = [f"Title: {row['title']}", f"Summary: {row['summary']}"]
    if str(row.get("authors_joined", "")).strip():
        parts.append(f"Authors: {row['authors_joined']}")
    if str(row.get("categories_joined", "")).strip():
        parts.append(f"Categories: {row['categories_joined']}")
    return normalize_whitespace(" ".join(parts))


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Clean raw records into an embed-ready dataframe.

    Contract (see phase1.py):
    - Returns exactly the 10 columns in ``CLEAN_COLUMNS``.
    - ``paper_id`` is non-null and unique.
    - ``text_for_embedding`` is non-empty.
    - ``age_days`` is computed from ``published`` relative to ``run_date``.
    """
    rows: list[dict[str, Any]] = []
    for record in records:
        paper_id = _safe_str(_record_field(record, "paper_id"))
        title = _safe_str(_record_field(record, "title"))
        summary = _safe_str(_record_field(record, "summary"))
        authors = [
            _safe_str(author) for author in _as_list(_record_field(record, "authors")) if _safe_str(author)
        ]
        categories = [
            _safe_str(category)
            for category in _as_list(_record_field(record, "categories"))
            if _safe_str(category)
        ]
        published = _parse_date(_record_field(record, "published")) or _parse_date(
            _record_field(record, "updated")
        )

        rows.append(
            {
                "paper_id": paper_id,
                "title": title,
                "summary": summary,
                "published": published.isoformat() if published else "",
                "authors_joined": compact_join(authors),
                "categories_joined": compact_join(categories),
                "age_days": (run_date.date() - published).days if published else None,
                "text_for_embedding": "",
                "abs_url": _safe_str(_record_field(record, "abs_url")),
                "pdf_url": _safe_str(_record_field(record, "pdf_url")),
            }
        )

    df = pd.DataFrame(rows, columns=CLEAN_COLUMNS)

    # Drop invalid records: missing id/title/summary, unparseable date, and
    # duplicate paper ids. Every filter is a deliberate, traceable rule.
    df = df[df["paper_id"].astype(str).str.strip().ne("")]
    df = df[df["title"].astype(str).str.strip().ne("")]
    df = df[df["summary"].astype(str).str.strip().ne("")]
    df = df[df["age_days"].notna()]
    df = df.drop_duplicates(subset="paper_id", keep="first")

    df["age_days"] = df["age_days"].astype(int)
    df["text_for_embedding"] = df.apply(_build_text, axis=1)
    df = df[df["text_for_embedding"].astype(str).str.strip().ne("")]

    # Keep exactly the contract columns and sort newest-first so the "latest
    # records" concept used by the corruption flow is well defined.
    df = df[CLEAN_COLUMNS].copy()
    df = df.sort_values("published", ascending=False).reset_index(drop=True)
    return df

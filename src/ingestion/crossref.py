from __future__ import annotations

import dataclasses
import html
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from core.utils import read_json, write_json

from core.config import Settings

logger = logging.getLogger(__name__)

_CROSSREF_API_URL = "https://api.crossref.org/works"
_USER_AGENT = "K3-Day10-Data-Observability-Lab/1.0"
_REQUEST_TIMEOUT = 30
_MAX_RETRIES = 4
_RETRY_STATUS_CODES = {429, 503}


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _clean_text(text: Any) -> str:
    """Strip XML/HTML tags, unescape HTML entities, and normalize whitespace."""
    if text is None:
        return ""
    if not isinstance(text, str):
        try:
            text = str(text)
        except Exception:
            return ""
    # Remove all XML/HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Unescape HTML entities (&amp; &lt; etc.)
    text = html.unescape(text)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_date_parts(obj: Any) -> str:
    """Extract YYYY-MM-DD from a Crossref date object (date-parts or date-time)."""
    if not isinstance(obj, dict):
        return ""
    # Try date-parts first
    date_parts = obj.get("date-parts")
    if isinstance(date_parts, list) and date_parts:
        parts = date_parts[0]
        if isinstance(parts, list) and parts:
            try:
                year = int(parts[0])
                month = int(parts[1]) if len(parts) > 1 and parts[1] else 1
                day = int(parts[2]) if len(parts) > 2 and parts[2] else 1
                return f"{year:04d}-{month:02d}-{day:02d}"
            except (ValueError, TypeError):
                pass
    # Fallback: date-time field (ISO 8601 string)
    date_time = obj.get("date-time")
    if isinstance(date_time, str) and date_time:
        match = re.match(r"(\d{4}-\d{2}-\d{2})", date_time)
        if match:
            return match.group(1)
    return ""


def _extract_date(item: dict, field: str) -> str:
    """Safely extract a date string from a named Crossref field."""
    try:
        return _extract_date_parts(item.get(field))
    except Exception:
        return ""


def _get_published(item: dict) -> str:
    """Fallback chain for publication date."""
    for field in ("published", "published-online", "published-print", "issued", "created"):
        date_str = _extract_date(item, field)
        if date_str:
            return date_str
    return ""


def _get_updated(item: dict) -> str:
    """Fallback chain for update date."""
    for field in ("indexed", "deposited", "created"):
        date_str = _extract_date(item, field)
        if date_str:
            return date_str
    return ""


def _extract_authors(item: dict) -> list[str]:
    """Extract list of author name strings from a Crossref item."""
    raw_authors = item.get("author")
    if not isinstance(raw_authors, list):
        return []
    result: list[str] = []
    for author in raw_authors:
        if not isinstance(author, dict):
            continue
        given = (author.get("given") or "").strip()
        family = (author.get("family") or "").strip()
        name = (author.get("name") or "").strip()
        if given and family:
            result.append(f"{given} {family}")
        elif family:
            result.append(family)
        elif given:
            result.append(given)
        elif name:
            result.append(name)
    return result


def _extract_categories(item: dict) -> list[str]:
    """Extract categories with fallback: subject -> container-title -> group-title -> type.

    Crossref no longer provides `subject` for most records, so we fall back to
    container-title (journal name), group-title, and document type to ensure
    every record has at least one category for question generation.
    """
    candidates: list[str] = []
    for s in (item.get("subject") or []):
        candidates.append(str(s))
    container = item.get("container-title") or []
    if isinstance(container, list) and container:
        candidates.append(str(container[0]))
    if item.get("group-title"):
        candidates.append(str(item["group-title"]))
    if item.get("type"):
        candidates.append(str(item["type"]).replace("-", " ").title())

    seen: set[str] = set()
    result: list[str] = []
    for cat in candidates:
        cat = cat.strip()
        if cat and cat.lower() not in seen:
            seen.add(cat.lower())
            result.append(cat)
    return result


def _extract_pdf_url(item: dict) -> str:
    """Find the first PDF link from the link array."""
    links = item.get("link")
    if not isinstance(links, list):
        return ""
    for link in links:
        if not isinstance(link, dict):
            continue
        url = link.get("URL", "")
        content_type = link.get("content-type", "")
        if not isinstance(url, str):
            continue
        if (
            "pdf" in content_type.lower()
            or url.lower().endswith(".pdf")
            or ".pdf?" in url.lower()
        ):
            return url
    return ""


def _extract_comment(item: dict) -> str:
    """Extract a comment/note string; only return plain strings, skip dicts/lists."""
    for field in ("update-to", "relation"):
        val = item.get(field)
        if val is None:
            continue
        if isinstance(val, str):
            return val.strip()
        # Avoid returning repr of dicts/lists which produces noisy garbage strings
    return ""


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse Crossref payload into list of PaperRecord.

    Handles missing/malformed data gracefully; returns list of valid records.
    """
    records: list[PaperRecord] = []

    try:
        message = payload.get("message", {})
        if not isinstance(message, dict):
            return []
        items = message.get("items", [])
        if not isinstance(items, list):
            return []
    except Exception as exc:
        logger.warning("Failed to read payload structure: %s", exc)
        return []

    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            # paper_id
            doi = item.get("DOI")
            if not doi:
                continue
            paper_id = str(doi).strip()
            if not paper_id:
                continue

            # title
            raw_title = item.get("title")
            if isinstance(raw_title, list):
                raw_title = raw_title[0] if raw_title else ""
            title = _clean_text(raw_title)
            if not title:
                continue

            # summary (abstract)
            raw_abstract = item.get("abstract") or item.get("description") or ""
            if isinstance(raw_abstract, list):
                raw_abstract = " ".join(str(x) for x in raw_abstract)
            summary = _clean_text(raw_abstract)

            # authors
            authors = _extract_authors(item)

            # categories
            categories = _extract_categories(item)
            primary_category = categories[0] if categories else ""

            # dates
            published = _get_published(item)
            updated = _get_updated(item)

            # abs_url
            abs_url = item.get("URL") or ""
            if not abs_url:
                abs_url = f"https://doi.org/{paper_id}"

            # pdf_url
            pdf_url = _extract_pdf_url(item)

            # comment
            comment = _extract_comment(item)

            records.append(
                PaperRecord(
                    paper_id=paper_id,
                    title=title,
                    summary=summary,
                    authors=authors,
                    categories=categories,
                    primary_category=primary_category,
                    published=published,
                    updated=updated,
                    abs_url=abs_url,
                    pdf_url=pdf_url,
                    comment=comment,
                )
            )
        except Exception as exc:
            logger.warning("Skipping malformed record: %s", exc)
            continue

    return records


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Call Crossref API, save raw artifacts, parse and return PaperRecord list."""
    params: dict[str, Any] = {
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
    }
    headers = {"User-Agent": _USER_AGENT}

    response_data: dict = {}
    last_status: int = 0

    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = requests.get(
                _CROSSREF_API_URL,
                params=params,
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            last_status = resp.status_code

            if resp.status_code in _RETRY_STATUS_CODES:
                retry_after = resp.headers.get("Retry-After")
                if retry_after:
                    try:
                        wait = float(retry_after)
                    except ValueError:
                        wait = 2 ** attempt
                else:
                    wait = 2 ** attempt
                if attempt < _MAX_RETRIES:
                    logger.warning(
                        "HTTP %s – retrying in %.0fs (attempt %d/%d)",
                        resp.status_code,
                        wait,
                        attempt + 1,
                        _MAX_RETRIES,
                    )
                    time.sleep(wait)
                    continue
                else:
                    raise RuntimeError(
                        f"Crossref API returned HTTP {resp.status_code} after "
                        f"{_MAX_RETRIES} retries."
                    )

            resp.raise_for_status()
            response_data = resp.json()
            break

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            if attempt < _MAX_RETRIES:
                wait = 2 ** attempt
                logger.warning("Request error (%s) – retrying in %.0fs", type(exc).__name__, wait)
                time.sleep(wait)
                continue
            raise

    if not response_data:
        raise RuntimeError(
            f"No data received from Crossref API (last status: {last_status})."
        )

    # Save raw API response
    raw_path: Path = settings.paths.raw_api_response
    write_json(raw_path, response_data)
    logger.info("Saved raw API response → %s", raw_path)

    # Parse records
    records = parse_crossref_payload(response_data)
    logger.info("Parsed %d valid records from Crossref response", len(records))

    # Save parsed records
    records_path: Path = settings.paths.raw_records_json
    write_json(records_path, [dataclasses.asdict(r) for r in records])
    logger.info("Saved parsed records → %s", records_path)

    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Load PaperRecord list from a JSON snapshot file."""
    if not path.exists():
        raise FileNotFoundError(
            f"Raw records file not found: {path}. "
            "Run fetch_source_records() first to generate it."
        )

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list in {path}, got {type(data).__name__}.")

    records: list[PaperRecord] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        paper_id = str(entry.get("paper_id", "")).strip()
        title = str(entry.get("title", "")).strip()
        if not paper_id or not title:
            continue
        try:
            records.append(
                PaperRecord(
                    paper_id=paper_id,
                    title=title,
                    summary=str(entry.get("summary", "")),
                    authors=list(entry.get("authors", [])),
                    categories=list(entry.get("categories", [])),
                    primary_category=str(entry.get("primary_category", "")),
                    published=str(entry.get("published", "")),
                    updated=str(entry.get("updated", "")),
                    abs_url=str(entry.get("abs_url", "")),
                    pdf_url=str(entry.get("pdf_url", "")),
                    comment=str(entry.get("comment", "")),
                )
            )
        except Exception as exc:
            logger.warning("Skipping invalid record entry: %s", exc)

    return records

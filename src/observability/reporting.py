from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.utils import now_utc, write_text

_COMPARE_METRICS = (
    ("retrieval_hit_rate", "Retrieval hit rate"),
    ("mean_token_f1", "Mean token F1"),
    ("judge_accuracy", "Judge accuracy"),
    ("mean_judge_score", "Mean judge score"),
)


def _fmt_value(value: Any) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        return f"{value:.4f}"
    if value is None:
        return "-"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _kv_table(title: str, data: dict[str, Any] | None) -> str:
    if not data:
        return f"### {title}\n\n_No data available._\n"
    lines = [f"### {title}", "", "| Field | Value |", "| --- | --- |"]
    for key, value in data.items():
        lines.append(f"| {key} | {_fmt_value(value)} |")
    return "\n".join(lines) + "\n"


def _metrics_section(title: str, metrics: dict[str, Any] | None) -> str:
    if not metrics:
        return f"### {title}\n\n_No data available._\n"

    lines = [f"### {title}", "", "| Metric | Value |", "| --- | --- |"]
    known_keys = {key for key, _ in _COMPARE_METRICS} | {"samples", "ragas"}
    for key, label in (("samples", "Samples"),) + _COMPARE_METRICS:
        if key in metrics:
            lines.append(f"| {label} | {_fmt_value(metrics[key])} |")
    for key, value in metrics.items():
        if key not in known_keys:
            lines.append(f"| {key} | {_fmt_value(value)} |")

    if "ragas" in metrics:
        ragas_val = metrics["ragas"]
        lines.append("")
        lines.append("**Ragas:**")
        if isinstance(ragas_val, dict):
            for key, value in ragas_val.items():
                lines.append(f"- {key}: {_fmt_value(value)}")
        else:
            lines.append(f"- {_fmt_value(ragas_val)}")

    return "\n".join(lines) + "\n"


def _quality_section(title: str, quality: dict[str, Any] | None) -> str:
    if not quality:
        return f"### {title}\n\n_No data available._\n"

    status = "PASSED" if quality.get("passed") else "FAILED"
    lines = [
        f"### {title} — {status}",
        "",
        f"- Report name: {quality.get('report_name', '-')}",
        f"- Total rows: {quality.get('total_rows', '-')}",
        f"- Generated at: {quality.get('generated_at', '-')}",
        "",
        "| Check | Result | Detail |",
        "| --- | --- | --- |",
    ]
    for check in quality.get("checks", []):
        mark = "PASS" if check.get("passed") else "FAIL"
        lines.append(f"| {check.get('name', '-')} | {mark} | {check.get('detail', '-')} |")
    return "\n".join(lines) + "\n"


def _freshness_section(title: str, freshness: dict[str, Any] | None) -> str:
    if not freshness:
        return f"### {title}\n\n_No data available._\n"

    status = "FRESH" if freshness.get("is_fresh") else "STALE"
    lines = [
        f"### {title} — {status}",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Freshness threshold (days) | {freshness.get('freshness_threshold_days', '-')} |",
        f"| Latest published | {freshness.get('latest_published', '-')} |",
        f"| Oldest published | {freshness.get('oldest_published', '-')} |",
        f"| Stale rows | {freshness.get('stale_rows', '-')} / {freshness.get('total_rows', '-')} |",
        f"| Generated at | {freshness.get('generated_at', '-')} |",
    ]
    return "\n".join(lines) + "\n"


def _delta(base: Any, other: Any) -> str:
    if not isinstance(base, (int, float)) or not isinstance(other, (int, float)):
        return "-"
    diff = other - base
    arrow = "up" if diff > 0 else "down" if diff < 0 else "flat"
    return f"{diff:+.4f} ({arrow})"


def _metrics_comparison_table(
    baseline: dict[str, Any] | None,
    corrupted: dict[str, Any] | None,
    repaired: dict[str, Any] | None,
) -> str:
    baseline = baseline or {}
    corrupted = corrupted or {}
    repaired = repaired or {}

    lines = [
        "| Metric | Baseline | Corrupted | Repaired | Corrupted vs Baseline | Repaired vs Baseline |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for key, label in _COMPARE_METRICS:
        base_val = baseline.get(key)
        corr_val = corrupted.get(key)
        rep_val = repaired.get(key)
        lines.append(
            f"| {label} | {_fmt_value(base_val)} | {_fmt_value(corr_val)} | {_fmt_value(rep_val)} "
            f"| {_delta(base_val, corr_val)} | {_delta(base_val, rep_val)} |"
        )
    return "\n".join(lines) + "\n"


def _takeaways(
    baseline: dict[str, Any] | None,
    corrupted: dict[str, Any] | None,
    repaired: dict[str, Any] | None,
) -> str:
    baseline = baseline or {}
    corrupted = corrupted or {}
    repaired = repaired or {}

    lines: list[str] = []
    for key, label in _COMPARE_METRICS:
        base_val, corr_val, rep_val = baseline.get(key), corrupted.get(key), repaired.get(key)
        if not all(isinstance(v, (int, float)) for v in (base_val, corr_val, rep_val)):
            continue
        drop = base_val - corr_val
        recovered = rep_val - corr_val
        if drop > 0:
            lines.append(
                f"- **{label}** dropped by {drop:.4f} after corruption "
                f"({base_val:.4f} -> {corr_val:.4f}); repair recovered {recovered:+.4f} (-> {rep_val:.4f})."
            )
        else:
            lines.append(
                f"- **{label}** did not drop after corruption "
                f"({base_val:.4f} -> {corr_val:.4f} -> {rep_val:.4f})."
            )

    if not lines:
        return "_Not enough numeric metrics to summarize._\n"
    return "\n".join(lines) + "\n"


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Write the baseline-phase markdown report: source summary, evaluation
    metrics, data quality checks, and freshness status."""
    sections = [
        "# Phase 1 - Baseline Pipeline Report",
        "",
        f"_Generated at {now_utc().isoformat()}_",
        "",
        "## 1. Source",
        "",
        _kv_table("Source summary", source_summary),
        "## 2. Evaluation metrics",
        "",
        _metrics_section("Retrieval / evaluation metrics", metrics),
        "## 3. Data quality",
        "",
        _quality_section("Data quality checks", quality),
        "## 4. Freshness",
        "",
        _freshness_section("Freshness report", freshness),
    ]
    write_text(Path(report_path), "\n".join(sections) + "\n")


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> None:
    """Write the markdown report comparing baseline vs corrupted vs repaired:
    metrics side-by-side, quality/freshness for corrupted and repaired, and an
    auto-generated takeaways section."""
    sections = [
        "# Corruption Impact Report",
        "",
        f"_Generated at {now_utc().isoformat()}_",
        "",
        "## 1. Metrics comparison",
        "",
        _metrics_comparison_table(baseline_metrics, corrupted_metrics, repaired_metrics),
        "## 2. Data quality — corrupted vs repaired",
        "",
        _quality_section("Corrupted dataset quality", corrupted_quality),
        _quality_section("Repaired dataset quality", repaired_quality),
        "## 3. Freshness — corrupted vs repaired",
        "",
        _freshness_section("Corrupted dataset freshness", corrupted_freshness),
        _freshness_section("Repaired dataset freshness", repaired_freshness),
        "## 4. Takeaways",
        "",
        _takeaways(baseline_metrics, corrupted_metrics, repaired_metrics),
    ]
    write_text(Path(report_path), "\n".join(sections) + "\n")

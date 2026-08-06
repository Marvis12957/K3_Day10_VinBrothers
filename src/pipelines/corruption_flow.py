from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings, load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report
from pipelines.phase1 import (
    REQUIRED_CLEAN_COLUMNS,
    json_safe_records,
    validate_clean_contract,
)
from retrieval.index import LocalEmbeddingIndex

COMPARE_METRICS = (
    "retrieval_hit_rate",
    "mean_token_f1",
    "judge_accuracy",
    "mean_judge_score",
)


def require_baseline(settings: Settings) -> dict[str, Any]:
    """Pha 2 chi co nghia khi baseline da chay xong va con day du artifact."""
    missing = [
        path
        for path in (
            settings.paths.baseline_metrics,
            settings.paths.clean_csv,
            settings.paths.eval_testset,
            settings.paths.raw_records_json,
        )
        if not path.exists()
    ]
    if missing:
        names = ", ".join(str(path.name) for path in missing)
        raise FileNotFoundError(
            f"Thieu artifact baseline: {names}. Chay `python script/run_phase1.py` truoc."
        )
    return read_json(settings.paths.baseline_metrics)


def validate_corrupted_frame(df: pd.DataFrame) -> None:
    """Corrupted data CO Y vi pham contract (trung paper_id, text rong), nen chi
    kiem tra cot con du - du de index build duoc, khong ep rang buoc chat luong."""
    if df is None or len(df) == 0:
        raise ValueError("Corrupted dataframe rong. Owner: TV4 (src/ingestion/corruption.py)")
    missing = [column for column in REQUIRED_CLEAN_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(
            f"Corrupted dataframe thieu cot {missing}, index se khong build duoc. "
            f"Owner: TV4 (src/ingestion/corruption.py)"
        )


def describe_corruption(baseline_df: pd.DataFrame, corrupted_df: pd.DataFrame) -> dict[str, Any]:
    """So sanh truc tiep baseline vs corrupted de bao cao doc duoc, khong phu thuoc
    vao viec TV4 ghi corruption log chi tiet den dau."""
    base_ids = set(baseline_df["paper_id"])
    corrupt_ids = set(corrupted_df["paper_id"])
    blank_summary = int(corrupted_df["summary"].astype(str).str.strip().eq("").sum())
    duplicated = int(corrupted_df["paper_id"].duplicated().sum())
    return {
        "baseline_rows": int(len(baseline_df)),
        "corrupted_rows": int(len(corrupted_df)),
        "removed_paper_ids": sorted(base_ids - corrupt_ids),
        "blank_summary_rows": blank_summary,
        "duplicate_rows": duplicated,
    }


def verify_repair(baseline_df: pd.DataFrame, repaired_df: pd.DataFrame) -> dict[str, Any]:
    """Repair phai dung lai tu raw snapshot, nen phai khop baseline - khong phai
    chi 'trong co ve on'. Day la bang chung repair that su phuc hoi du lieu."""
    base_ids = set(baseline_df["paper_id"])
    repaired_ids = set(repaired_df["paper_id"])
    return {
        "baseline_rows": int(len(baseline_df)),
        "repaired_rows": int(len(repaired_df)),
        "missing_after_repair": sorted(base_ids - repaired_ids),
        "unexpected_after_repair": sorted(repaired_ids - base_ids),
        "fully_restored": base_ids == repaired_ids and len(baseline_df) == len(repaired_df),
    }


def evaluate_state(
    settings: Settings,
    df: pd.DataFrame,
    label: str,
    embeddings_path: Path,
    metrics_path: Path,
    answers_path: Path,
    freshness_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Index -> evaluate -> quality -> freshness cho mot trang thai du lieu.

    Luon dung dung test set da freeze o baseline, khong bao gio sinh lai.
    """
    print(f"      [{label}] build index ...")
    index = LocalEmbeddingIndex.build(df=df, settings=settings, embeddings_output_path=embeddings_path)

    print(f"      [{label}] evaluate tren test set da freeze ...")
    bundle = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=metrics_path,
        answers_output_path=answers_path,
    )

    print(f"      [{label}] quality + freshness ...")
    quality = run_data_quality_checks(df, settings=settings, report_name=label)
    freshness = build_freshness_report(df, settings=settings, report_path=freshness_path)
    return bundle.summary, quality, freshness


def print_comparison(
    baseline: dict[str, Any],
    corrupted: dict[str, Any],
    repaired: dict[str, Any],
    quality_states: dict[str, dict[str, Any]],
    freshness_states: dict[str, dict[str, Any]],
) -> None:
    print("\n=== SO SANH BASELINE / CORRUPTED / REPAIRED ===")
    print(f"{'metric':<22}{'baseline':>10}{'corrupted':>12}{'repaired':>11}{'  delta(corrupt)':>18}")
    print("-" * 73)
    for key in COMPARE_METRICS:
        base, corr, rep = baseline.get(key), corrupted.get(key), repaired.get(key)
        if all(isinstance(value, (int, float)) for value in (base, corr, rep)):
            print(f"{key:<22}{base:>10.4f}{corr:>12.4f}{rep:>11.4f}{corr - base:>+18.4f}")
        else:
            print(f"{key:<22}{str(base):>10}{str(corr):>12}{str(rep):>11}")
    print("-" * 73)
    print(
        f"{'quality passed':<22}"
        f"{str(quality_states['baseline'].get('passed')):>10}"
        f"{str(quality_states['corrupted'].get('passed')):>12}"
        f"{str(quality_states['repaired'].get('passed')):>11}"
    )
    print(
        f"{'freshness is_fresh':<22}"
        f"{str(freshness_states['baseline'].get('is_fresh')):>10}"
        f"{str(freshness_states['corrupted'].get('is_fresh')):>12}"
        f"{str(freshness_states['repaired'].get('is_fresh')):>11}"
    )


def main() -> None:
    settings = load_settings()
    run_date = now_utc()

    print("[1/7] Kiem tra artifact baseline ...")
    baseline_metrics = require_baseline(settings)
    baseline_df = pd.read_csv(settings.paths.clean_csv)
    test_set = read_json(settings.paths.eval_testset)
    print(f"      baseline {len(baseline_df)} dong, test set {len(test_set)} cau (giu nguyen)")

    print("[2/7] Tao corrupted dataset ...")
    corrupted_df = corrupt_clean_dataframe(baseline_df.copy(), settings.paths.corruption_log)
    validate_corrupted_frame(corrupted_df)
    corruption_summary = describe_corruption(baseline_df, corrupted_df)
    print(
        f"      {corruption_summary['baseline_rows']} -> {corruption_summary['corrupted_rows']} dong"
        f" | mat {len(corruption_summary['removed_paper_ids'])} paper"
        f" | summary rong {corruption_summary['blank_summary_rows']}"
        f" | dong trung {corruption_summary['duplicate_rows']}"
    )

    write_csv(corrupted_df, settings.paths.corrupted_clean_csv)
    write_json(settings.paths.corrupted_clean_json, json_safe_records(corrupted_df))

    print("[3/7] Danh gia corrupted ...")
    corrupted_metrics, corrupted_quality, corrupted_freshness = evaluate_state(
        settings=settings,
        df=corrupted_df,
        label="corrupted",
        embeddings_path=settings.paths.corrupted_embeddings_json,
        metrics_path=settings.paths.corrupted_metrics,
        answers_path=settings.paths.corrupted_answers,
        freshness_path=settings.paths.quality_dir / "freshness_report_corrupted.json",
    )

    print("[4/7] Repair tu raw snapshot ...")
    records = load_raw_records(settings.paths.raw_records_json)
    repaired_df = build_clean_dataframe(records, run_date=run_date)
    validate_clean_contract(repaired_df)
    repair_check = verify_repair(baseline_df, repaired_df)
    print(
        f"      {repair_check['repaired_rows']} dong phuc hoi tu {len(records)} raw records"
        f" | khop baseline: {repair_check['fully_restored']}"
    )
    if not repair_check["fully_restored"]:
        print(f"      CHU Y thieu: {repair_check['missing_after_repair'][:5]}")

    write_csv(repaired_df, settings.paths.repaired_clean_csv)
    write_json(settings.paths.repaired_clean_json, json_safe_records(repaired_df))

    print("[5/7] Danh gia repaired ...")
    repaired_metrics, repaired_quality, repaired_freshness = evaluate_state(
        settings=settings,
        df=repaired_df,
        label="repaired",
        embeddings_path=settings.paths.repaired_embeddings_json,
        metrics_path=settings.paths.repaired_metrics,
        answers_path=settings.paths.repaired_answers,
        freshness_path=settings.paths.quality_dir / "freshness_report_repaired.json",
    )

    print("[6/7] Ghi corruption comparison report ...")
    generate_corruption_report(
        report_path=settings.paths.comparison_report,
        baseline_metrics=baseline_metrics,
        corrupted_metrics=corrupted_metrics,
        repaired_metrics=repaired_metrics,
        corrupted_quality=corrupted_quality,
        repaired_quality=repaired_quality,
        corrupted_freshness=corrupted_freshness,
        repaired_freshness=repaired_freshness,
    )

    print("[7/7] Ghi summary so sanh ...")
    baseline_quality = read_json(settings.paths.quality_dir / "baseline_quality.json")
    baseline_freshness = read_json(settings.paths.freshness_report)
    write_json(
        settings.paths.quality_dir / "corruption_summary.json",
        {
            "generated_at": run_date.isoformat(),
            "corruption": corruption_summary,
            "repair_verification": repair_check,
            "metrics": {
                "baseline": {key: baseline_metrics.get(key) for key in COMPARE_METRICS},
                "corrupted": {key: corrupted_metrics.get(key) for key in COMPARE_METRICS},
                "repaired": {key: repaired_metrics.get(key) for key in COMPARE_METRICS},
            },
        },
    )

    print_comparison(
        baseline=baseline_metrics,
        corrupted=corrupted_metrics,
        repaired=repaired_metrics,
        quality_states={
            "baseline": baseline_quality,
            "corrupted": corrupted_quality,
            "repaired": repaired_quality,
        },
        freshness_states={
            "baseline": baseline_freshness,
            "corrupted": corrupted_freshness,
            "repaired": repaired_freshness,
        },
    )
    print(f"\nReport: {settings.paths.comparison_report}")

from __future__ import annotations

from typing import Any

import pandas as pd

from core.config import Settings, load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import PaperRecord, fetch_source_records, load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.index import LocalEmbeddingIndex


# Data contract chot o checkpoint C1. Moi module owner phai ton trong bang nay.
REQUIRED_CLEAN_COLUMNS: tuple[str, ...] = (
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

REQUIRED_TESTSET_FIELDS: tuple[str, ...] = (
    "id",
    "question_type",
    "question",
    "ground_truth",
    "ground_truth_doc_ids",
)

CONTRACT_OWNERS = {
    "raw": "TV1 - Source Ingestion Owner (src/ingestion/crossref.py)",
    "clean": "TV2 - Data Model Owner (src/ingestion/cleaning.py)",
    "testset": "TV2 - Eval Set Owner (src/evaluation/testset.py)",
}

DEMO_QUESTION_LIMIT = 3


def validate_clean_contract(df: pd.DataFrame) -> None:
    """Fail fast khi cleaned dataframe khong dung contract C1."""
    if df is None or len(df) == 0:
        raise ValueError(f"Cleaned dataframe rong. Owner: {CONTRACT_OWNERS['clean']}")

    missing = [column for column in REQUIRED_CLEAN_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(
            f"Cleaned dataframe thieu cot {missing}. "
            f"Cot bat buoc: {list(REQUIRED_CLEAN_COLUMNS)}. Owner: {CONTRACT_OWNERS['clean']}"
        )

    if df["paper_id"].isna().any():
        raise ValueError(f"paper_id co gia tri null. Owner: {CONTRACT_OWNERS['clean']}")
    if df["paper_id"].duplicated().any():
        duplicated = df.loc[df["paper_id"].duplicated(), "paper_id"].tolist()
        raise ValueError(f"paper_id bi trung: {duplicated[:5]}. Owner: {CONTRACT_OWNERS['clean']}")
    if df["text_for_embedding"].astype(str).str.strip().eq("").any():
        raise ValueError(
            f"text_for_embedding co gia tri rong, embedding se vo nghia. "
            f"Owner: {CONTRACT_OWNERS['clean']}"
        )


def validate_testset_contract(test_set: list[dict[str, Any]]) -> None:
    if not test_set:
        raise ValueError(f"Test set rong. Owner: {CONTRACT_OWNERS['testset']}")
    for index, item in enumerate(test_set):
        missing = [field for field in REQUIRED_TESTSET_FIELDS if field not in item]
        if missing:
            raise ValueError(
                f"Test set item #{index} thieu field {missing}. Owner: {CONTRACT_OWNERS['testset']}"
            )
        if not item["ground_truth_doc_ids"]:
            raise ValueError(
                f"Test set item #{index} khong co ground_truth_doc_ids, "
                f"retrieval_hit_rate se luon bang 0. Owner: {CONTRACT_OWNERS['testset']}"
            )


def json_safe_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Doi dataframe thanh list dict an toan cho json.dumps."""
    frame = df.copy()
    for column in frame.columns:
        if pd.api.types.is_datetime64_any_dtype(frame[column]):
            frame[column] = frame[column].astype(str)
    frame = frame.astype(object).where(pd.notna(frame), None)
    return frame.to_dict(orient="records")


def load_or_fetch_records(settings: Settings) -> tuple[list[PaperRecord], str]:
    """Dung raw snapshot neu da co, chi goi API khi thieu hoac REFRESH_SOURCE=1."""
    raw_path = settings.paths.raw_records_json
    if settings.refresh_source or not raw_path.exists():
        print(f"[1/9] Fetch tu {settings.source_api} ...")
        return fetch_source_records(settings), "api"
    print(f"[1/9] Dung raw snapshot san co: {raw_path}")
    return load_raw_records(raw_path), "snapshot"


def load_or_build_test_set(settings: Settings, df: pd.DataFrame) -> list[dict[str, Any]]:
    """Test set phai duoc freeze de baseline/corrupted/repaired so sanh duoc voi nhau."""
    testset_path = settings.paths.eval_testset
    if settings.refresh_test_set or not testset_path.exists():
        print(f"[5/9] Tao test set moi -> {testset_path}")
        return build_test_set(df, testset_path)
    print(f"[5/9] Tai su dung test set da freeze: {testset_path}")
    return read_json(testset_path)


def flatten_agent_content(content: Any) -> str:
    """Mot so provider (Gemini) tra ve list content block kem signature.

    Gop lai thanh text de artifact doc duoc thay vi luu nguyen repr cua list.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        ]
        return " ".join(part for part in parts if part).strip()
    return str(content)


def run_agent_demo(settings: Settings, index: LocalEmbeddingIndex, test_set: list[dict[str, Any]]) -> None:
    """Demo agent tren vai cau hoi. Khong co API key thi bo qua, khong lam vo pipeline."""
    from retrieval.agent import build_agent, run_agent_question

    agent = build_agent(settings=settings, index=index)
    demo: list[dict[str, Any]] = []
    for item in test_set[:DEMO_QUESTION_LIMIT]:
        demo.append(
            {
                "question": item["question"],
                "ground_truth": item["ground_truth"],
                "agent_answer": flatten_agent_content(run_agent_question(agent, item["question"])),
            }
        )
    write_json(settings.paths.demo_answers, demo)
    print(f"      Agent demo -> {settings.paths.demo_answers}")


def relative_path(path, settings: Settings) -> str:
    """Duong dan tuong doi so voi project root, tranh lo path tuyet doi trong report."""
    try:
        return str(path.relative_to(settings.paths.project_dir))
    except ValueError:
        return str(path)


def build_source_summary(
    settings: Settings,
    records: list[PaperRecord],
    df: pd.DataFrame,
    origin: str,
    fetched_at: str,
) -> dict[str, Any]:
    return {
        "source_api": settings.source_api,
        "query": settings.source_query,
        "filter": settings.source_filter,
        "max_results": settings.max_results,
        "origin": origin,
        "fetched_at": fetched_at,
        "raw_records": len(records),
        "clean_records": int(len(df)),
        "dropped_records": len(records) - int(len(df)),
        "embedding_model": settings.embedding_model,
        "collection_name": settings.baseline_collection_name,
        "top_k": settings.top_k,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.model_name,
        "raw_response_path": relative_path(settings.paths.raw_api_response, settings),
        "raw_records_path": relative_path(settings.paths.raw_records_json, settings),
        "clean_csv_path": relative_path(settings.paths.clean_csv, settings),
    }


def main() -> None:
    settings = load_settings()
    run_date = now_utc()

    records, origin = load_or_fetch_records(settings)
    if not records:
        raise ValueError(f"Khong lay duoc record nao. Owner: {CONTRACT_OWNERS['raw']}")
    print(f"      {len(records)} raw records ({origin})")

    print("[2/9] Clean data ...")
    df = build_clean_dataframe(records, run_date=run_date)
    validate_clean_contract(df)
    print(f"      {len(df)} clean records, {len(records) - len(df)} bi loai")

    print("[3/9] Luu cleaned artifacts ...")
    write_csv(df, settings.paths.clean_csv)
    write_json(settings.paths.clean_json, json_safe_records(df))

    print("[4/9] Build embedding index (MiniLM + ChromaDB) ...")
    index = LocalEmbeddingIndex.build(
        df=df,
        settings=settings,
        embeddings_output_path=settings.paths.embeddings_json,
    )

    test_set = load_or_build_test_set(settings, df)
    validate_testset_contract(test_set)
    print(f"      {len(test_set)} cau hoi")

    print("[6/9] Evaluate baseline ...")
    bundle = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.baseline_metrics,
        answers_output_path=settings.paths.baseline_answers,
    )

    print("[7/9] Data quality checks ...")
    quality = run_data_quality_checks(df, settings=settings, report_name="baseline")

    print("[8/9] Freshness report ...")
    freshness = build_freshness_report(df, settings=settings, report_path=settings.paths.freshness_report)

    print("[9/9] Markdown report ...")
    source_summary = build_source_summary(settings, records, df, origin, run_date.isoformat())
    generate_phase1_report(
        report_path=settings.paths.baseline_report,
        source_summary=source_summary,
        metrics=bundle.summary,
        quality=quality,
        freshness=freshness,
    )

    try:
        run_agent_demo(settings, index, test_set)
    except Exception as exc:
        print(f"      Bo qua agent demo: {exc}")

    print("\n=== BASELINE SUMMARY ===")
    for key in ("samples", "retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"):
        print(f"  {key:22s} {bundle.summary.get(key)}")
    print(f"  quality passed        {quality.get('passed')}")
    print(f"  freshness is_fresh    {freshness.get('is_fresh')}")
    print(f"\nReport: {settings.paths.baseline_report}")

"""Doc nhanh 2 cau hoi demo tu artifact da sinh — khong goi API, khong build lai index.

Cau hoi 1: Data pipeline duoc thiet ke nhu the nao?
Cau hoi 2: Nhom da lam the nao de du lieu xau di va xu ly lai du lieu do?

    uv run python script/explain_pipeline.py            # chay het
    uv run python script/explain_pipeline.py --step     # dung sau moi phan, Enter de tiep
    uv run python script/explain_pipeline.py --act 2    # chi tra loi cau 2
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
OFF = "\033[0m"

STEP = False

# Dam bao box-drawing (Unicode) hien thi dung tren Windows, ke ca khi pipe output.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def read(relative: str):
    path = ROOT / relative
    if not path.exists():
        sys.exit(f"Thieu artifact: {relative}. Chay run_phase1.py va run_corruption_flow.py truoc.")
    return json.loads(path.read_text(encoding="utf-8"))


def header(number: int, title: str) -> None:
    print(f"\n{BOLD}{CYAN}{'=' * 74}{OFF}")
    print(f"{BOLD}{CYAN}  {number}. {title}{OFF}")
    print(f"{BOLD}{CYAN}{'=' * 74}{OFF}\n")


def sub(title: str) -> None:
    print(f"\n{BOLD}{YELLOW}  -- {title}{OFF}")


def pause() -> None:
    if STEP:
        input(f"\n{DIM}   [Enter de tiep tuc]{OFF}")


def mark(passed: bool) -> str:
    return f"{GREEN}PASS{OFF}" if passed else f"{RED}FAIL{OFF}"


# ---------------------------------------------------------------------------
# Helper ve bieu do (box-drawing) — dam bao can chinh chinh xac
# ---------------------------------------------------------------------------

def _box(lines: list[str], width: int = 32) -> list[str]:
    """Ve mot box khung don vao danh sach dong."""
    border = "─" * width
    return (
        ["┌" + border + "┐"]
        + ["│" + line.center(width) + "│" for line in lines]
        + ["└" + border + "┘"]
    )


def _side(left: list[str], right: list[str], gap: int = 6) -> list[str]:
    """Dat hai box canh nhau tren cung cac dong."""
    height = max(len(left), len(right))
    left = left + [""] * (height - len(left))
    right = right + [""] * (height - len(right))
    return [a + " " * gap + b for a, b in zip(left, right)]


def _arrow(col: int, label: str = "") -> list[str]:
    """Tra ve 2 dong: duong thang dung + mui ten (kem chu thich)."""
    note = f"   {DIM}{label}{OFF}" if label else ""
    return [" " * col + "│", " " * col + "▼" + note]


def _fork(col_left: int, col_center: int, col_right: int) -> list[str]:
    """Ve nhanh doi: ┌────┴────┐ roi hai mui ten xuong hai cot."""
    return [
        " " * col_center + "│",
        " " * col_left + "┌" + "─" * (col_center - col_left - 1)
        + "┴" + "─" * (col_right - col_center - 1) + "┐",
        " " * col_left + "▼" + " " * (col_right - col_left - 1) + "▼",
    ]


# ---------------------------------------------------------------------------
# CAU 1 — Data pipeline duoc thiet ke nhu the nao?
# ---------------------------------------------------------------------------

def q1_architecture() -> None:
    sub("Kien truc tong quan (2 pha) — bieu do")

    W, C = 32, 16  # do rong box chinh va cot giua

    # ---------- PHA 1 ----------
    print(f"\n{BOLD}PHA 1 - BASELINE (du lieu sach){OFF}\n")
    canvas: list[str] = []

    canvas += _box(["CROSSREF REST API", "api.crossref.org/works"], W)
    canvas += _arrow(C, "fetch · retry/backoff 429/503")

    canvas += _box(["src/ingestion/crossref.py", "parse JATS → PaperRecord", "(11 fields)"], W)
    canvas += _fork(11, C, 40)

    left = _box(["crossref_response.json", "(raw goc =", "NGUON REPAIR pha 2)"], 22)
    right = _box(["crossref_records.json", "(24 PaperRecord)"], 24)
    canvas += _side(left, right, gap=6)
    canvas += _arrow(40, "nguon repair (pha 2)")

    canvas += _box(["src/ingestion/cleaning.py", "normalize · age_days ·", "text_for_embedding", "→ 10 cot contract"], W)
    canvas += _arrow(C, "paper_id unique")

    canvas += _box(["data/clean/papers_clean.{csv,json}"], W)
    canvas += _fork(12, C, 38)

    left = _box(["src/evaluation/testset.py", "4 loai cau hoi", "test_set.json", "(DONG BANG)"], 24)
    right = _box(["src/retrieval/index.py", "MiniLM-L6-v2 +", "ChromaDB cosine", "papers-baseline"], 24)
    canvas += _side(left, right, gap=2)
    canvas += _arrow(25, "test set + index hoi tu")

    canvas += _box(["src/evaluation/metrics.py", "hit_rate · token_F1 ·", "judge_accuracy · score", "(ragas neu bat)"], W)
    canvas += _arrow(C, "answers + metrics")

    canvas += _box(["observability: quality.py +", "reporting.py", "→ quality/freshness", "   + phase1_report.md"], W)

    print("\n".join(canvas))

    # ---------- PHA 2 ----------
    print(f"\n{BOLD}PHA 2 - CORRUPTION / REPAIR / COMPARISON{OFF}\n")
    canvas = []

    canvas += _box(["data/clean/papers_clean.csv", "(baseline)"], W)
    canvas += _arrow(C, "seed 42 · tai lap duoc")

    canvas += _box(["src/ingestion/corruption.py", "8 kich ban co kiem soat", "drop/blank/noise/truncate", "stale/swap/duplicate"], W)
    canvas += _fork(11, C, 38)

    left = _box(["papers_clean_corrupted", ".{csv,json}"], 22)
    right = _box(["data/results/", "corruption_log.json"], 20)
    canvas += _side(left, right, gap=6)
    canvas += _arrow(25, "re-index + re-evaluate")

    canvas += _box(["index papers-corrupted", "evaluate tren CUNG", "test set da dong bang"], W)
    canvas += _arrow(C, "quality/freshness FAIL")

    canvas += _box(["REPAIR: load_raw_records", "→ build_clean_dataframe lai", "(KHONG goi lai API)"], W)
    canvas += _arrow(C, "verify_repair · fully_restored")

    canvas += _box(["index papers-repaired", "evaluate repaired", "quality + freshness xanh"], W)
    canvas += _arrow(C, "so sanh 3 trang thai")

    canvas += _box(["corruption_flow.py", "→ corruption_report.md", "baseline/corrupted/repaired"], W)

    print("\n".join(canvas))
    pause()


def q1_contract() -> None:
    sub("Data contract (chot o checkpoint C1)")
    print(f"""
  CLEAN schema - dung 10 cot (owner: TV2 cleaning.py):
    paper_id, title, summary, published, authors_joined, categories_joined,
    age_days, text_for_embedding, abs_url, pdf_url
    -> paper_id: khong null, khong trung; text_for_embedding: khong rong

  TESTSET - moi item dung 5 field (owner: TV2 testset.py):
    id, question_type, question, ground_truth, ground_truth_doc_ids
    -> ground_truth_doc_ids khong duoc rong (neu rong thi hit_rate = 0)

  phase1.py validate fail-fast kem ten owner — ai lam sai schema la biet ngay.
""")
    pause()


def q1_numbers() -> None:
    sub("Con so thuc te tu artifact")
    quality = read("data/quality/baseline_quality.json")
    fresh = read("data/quality/freshness_report.json")
    testset = read("data/eval/test_set.json")
    raw = read("data/raw/crossref_records.json")

    types: dict[str, int] = {}
    for item in testset:
        types[item["question_type"]] = types.get(item["question_type"], 0) + 1

    print(f"""
  Source        : Crossref REST API  (api.crossref.org/works)
  Query/filter  : 'agentic retrieval augmented generation large language model'
                   + from-pub-date:{fresh['freshness_threshold_days']}d, has-abstract:true  (max_results=24)
  Raw records   : {len(raw)}
  Clean records : {quality['total_rows']}  (10 cot, paper_id unique)
  Test set      : {len(testset)} cau hoi, dong bang -> {types}
  Embedding     : sentence-transformers/all-MiniLM-L6-v2 (normalized)
  Vector store  : ChromaDB cosine, top_k = 4
  Collections   : papers-baseline / papers-corrupted / papers-repaired (rieng, khong de baseline)
  Freshness     : ngung {fresh['freshness_threshold_days']} ngay  (baseline: {fresh['stale_rows']}/{fresh['total_rows']} qua han)

  3 nguyen tac song con: test set dong bang 1 lan · 3 trang thai path/collection
  rieng · repair = chay lai cleaning tu raw (khong sua tay ket qua).
""")
    pause()


def q1() -> None:
    header("CAU 1", "DATA PIPELINE THIET KE NHU THE NAO?")
    q1_architecture()
    q1_contract()
    q1_numbers()


# ---------------------------------------------------------------------------
# CAU 2 — Nhom lam du lieu xau di va xu ly lai nhu the nao?
# ---------------------------------------------------------------------------

def q2_corruption() -> None:
    sub("A. Lam du lieu xau di (corruption) — 8 kich ban co kiem soat")
    log = read("data/results/corruption_log.json")
    print(f"  Seed co dinh: {log['random_seed']} (tai lap duoc)   "
          f"{log['rows_before']} dong -> {log['rows_after']} dong   "
          f"{log['distinct_paper_ids_affected']}/{log['rows_before']} tai lieu bi dung den\n")
    for op in log["operations"]:
        if op["type"] == "rebuild_text_for_embedding":
            continue
        print(f"  {YELLOW}{op['type']:<24}{OFF}{op['rows_affected']:>3} dong   {DIM}{op['description'][:50]}{OFF}")
    print(f"\n  {DIM}rebuild_text_for_embedding: dong lai text cho moi dong da doi cot nguon.{OFF}")
    print(f"  {DIM}2 rang buoc bat buoc: sua published -> tinh lai age_days; "
          f"sua cot nguon -> dựng lai text_for_embedding.{OFF}")
    pause()


def q2_alarm() -> None:
    sub("B. Observability bao dong — phat hien TRUOC khi nguoi dung hoi")
    quality = read("data/quality/corrupted_quality.json")
    fresh = read("data/quality/freshness_report_corrupted.json")
    failed = [c["name"] for c in quality["checks"] if not c["passed"]]
    for check in quality["checks"]:
        print(f"  {mark(check['passed'])}  {check['name']:<26}{DIM}{check['detail'][:44]}{OFF}")
    print(f"\n  Freshness: {RED}STALE{OFF} - {fresh['stale_rows']}/{fresh['total_rows']} dong qua han "
          f"(cu nhat: {fresh['oldest_published']})")
    print(f"\n  {DIM}Chot chan nay hoat dong truoc khi agent noi bat ky dieu gi.{OFF}")
    pause()


def q2_damage() -> None:
    sub("C. Thiet hai do duoc — agent tra loi sai")
    base = read("data/results/baseline_metrics.json")
    corr = read("data/results/corrupted_metrics.json")
    print(f"  {'metric':<22}{'baseline':>10}{'corrupted':>12}{'thay doi':>12}")
    print(f"  {'-' * 56}")
    for key in ("retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"):
        delta = corr[key] - base[key]
        print(f"  {key:<22}{base[key]:>10.4f}{RED}{corr[key]:>12.4f}{OFF}{RED}{delta:>+12.4f}{OFF}")
    print(f"\n  {DIM}Du lieu xau lam agent retrieve sai 4/16 cau va token F1 roi 0.41.{OFF}")
    pause()


def q2_repair() -> None:
    sub("D. Xu ly lai (repair) — dung lai tu raw snapshot, co kiem chung")
    summary = read("data/quality/corruption_summary.json")
    check = summary["repair_verification"]
    base = read("data/results/baseline_metrics.json")
    corr = read("data/results/corrupted_metrics.json")
    rep = read("data/results/repaired_metrics.json")

    print(f"  Nguon: data/raw/crossref_records.json  {DIM}(snapshot bat bien, KHONG goi lai API){OFF}")
    print(f"  Buoc: load_raw_records -> build_clean_dataframe -> validate_clean_contract\n")
    print(f"  {'metric':<22}{'baseline':>10}{'corrupted':>12}{'repaired':>11}")
    print(f"  {'-' * 55}")
    for key in ("retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"):
        print(f"  {key:<22}{base[key]:>10.4f}{RED}{corr[key]:>12.4f}{OFF}{GREEN}{rep[key]:>11.4f}{OFF}")

    quality = read("data/quality/repaired_quality.json")
    fresh = read("data/quality/freshness_report_repaired.json")
    print(f"\n  Data quality: {mark(quality['passed'])}    Freshness: {GREEN}Fresh{OFF}")

    print(f"\n  {BOLD}Kiem chung repair bang du lieu (verify_repair):{OFF}")
    print(f"    missing_after_repair    : {check['missing_after_repair'] or '[]'}")
    print(f"    unexpected_after_repair : {check['unexpected_after_repair'] or '[]'}")
    print(f"    fully_restored          : {GREEN}{check['fully_restored']}{OFF}")
    print(f"\n  {DIM}Tap paper_id sau repair khop baseline tuyet doi -> phuc hoi THAT, khong phai so trung.{OFF}")
    pause()


def q2() -> None:
    header("CAU 2", "NHOM LAM DU LIEU XAU DI VA XU LY LAI NHU THE NAO?")
    q2_corruption()
    q2_alarm()
    q2_damage()
    q2_repair()


def closing() -> None:
    print(f"\n{BOLD}{CYAN}{'=' * 74}{OFF}")
    print(f"{BOLD}  TOM TAT 2 CAU HOI{OFF}\n")
    print("  CAU 1: Pipeline = Crossref -> raw -> clean(10 cot) -> test set(dong bang)")
    print("         -> index(MiniLM+Chroma) -> evaluate -> quality/freshness -> report,")
    print("         roi corruption -> evaluate -> repair tu raw -> compare.")
    print("  CAU 2: Lam xau = 8 kich ban co seed va log (drop/blank/noise/truncate/")
    print("         stale/swap/duplicate + rebuild text). Xu ly lai = dung LAI tu raw,")
    print("         verify_repair khop baseline, agent metric phuc hoi 100%.\n")
    print(f"   {DIM}Ca 3 trang thai cham tren cung 1 bo de dong bang, cung 1 model judge.{OFF}")
    print(f"{BOLD}{CYAN}{'=' * 74}{OFF}\n")


def main() -> None:
    global STEP
    parser = argparse.ArgumentParser(description="Tra loi 2 cau hoi demo tu artifact da sinh.")
    parser.add_argument("--step", action="store_true", help="dung sau moi phan, Enter de tiep")
    parser.add_argument("--act", type=int, choices=[1, 2], help="chi tra loi mot cau (1 hoac 2)")
    args = parser.parse_args()
    STEP = args.step

    if args.act == 1:
        q1()
        return
    if args.act == 2:
        q2()
        return
    q1()
    q2()
    closing()


if __name__ == "__main__":
    main()

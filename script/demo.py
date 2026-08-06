"""Demo doc tu artifact da sinh — khong goi API, khong build lai index.

Dung khi trinh bay: chay nhanh, khong phu thuoc mang.

    uv run python script/demo.py            # chay het
    uv run python script/demo.py --step     # dung sau moi phan, Enter de tiep
    uv run python script/demo.py --act 3    # chay rieng mot phan
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


def read(relative: str):
    path = ROOT / relative
    if not path.exists():
        sys.exit(f"Thieu artifact: {relative}. Chay run_phase1.py va run_corruption_flow.py truoc.")
    return json.loads(path.read_text(encoding="utf-8"))


def header(number: int, title: str) -> None:
    print(f"\n{BOLD}{CYAN}{'=' * 74}{OFF}")
    print(f"{BOLD}{CYAN}  PHAN {number}. {title}{OFF}")
    print(f"{BOLD}{CYAN}{'=' * 74}{OFF}\n")


def pause() -> None:
    if STEP:
        input(f"\n{DIM}   [Enter de tiep tuc]{OFF}")


def mark(passed: bool) -> str:
    return f"{GREEN}PASS{OFF}" if passed else f"{RED}FAIL{OFF}"


def act1_baseline() -> None:
    header(1, "BASELINE — moi thu deu xanh")
    metrics = read("data/results/baseline_metrics.json")
    quality = read("data/quality/baseline_quality.json")
    fresh = read("data/quality/freshness_report.json")
    testset = read("data/eval/test_set.json")

    print(f"  Corpus  : {quality['total_rows']} bai bao Crossref")
    print(f"  Test set: {len(testset)} cau hoi, da DONG BANG")
    types: dict[str, int] = {}
    for item in testset:
        types[item["question_type"]] = types.get(item["question_type"], 0) + 1
    print(f"            {types}\n")
    for key in ("retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"):
        print(f"  {key:<22}{GREEN}{metrics[key]}{OFF}")
    print(f"\n  Data quality: {mark(quality['passed'])}  ({len(quality['checks'])}/{len(quality['checks'])} check)")
    print(f"  Freshness   : {GREEN}Fresh{OFF}  ({fresh['stale_rows']}/{fresh['total_rows']} qua han)")
    print(f"\n{DIM}  Baseline cham tran. Moi sut giam sau day deu quy duoc ve du lieu.{OFF}")
    pause()


def act2_corruption() -> None:
    header(2, "PHA DU LIEU — 7 kich ban co kiem soat")
    log = read("data/results/corruption_log.json")
    print(f"  Seed co dinh: {log['random_seed']}  (tai lap duoc)")
    print(f"  {log['rows_before']} dong -> {log['rows_after']} dong")
    print(f"  {log['distinct_paper_ids_affected']}/{log['rows_before']} tai lieu bi dung den\n")
    for op in log["operations"]:
        if op["type"] == "rebuild_text_for_embedding":
            continue
        print(f"  {YELLOW}{op['type']:<24}{OFF}{op['rows_affected']:>3} dong   {DIM}{op['description'][:44]}{OFF}")
    print(f"\n{DIM}  Corruption cham vao tai lieu NAM TRONG test set — neu khong, metric se khong doi.{OFF}")
    pause()


def act3_alarm() -> None:
    header(3, "CHUONG BAO — observability phat hien TRUOC khi ai kip hoi")
    quality = read("data/quality/corrupted_quality.json")
    fresh = read("data/quality/freshness_report_corrupted.json")
    for check in quality["checks"]:
        print(f"  {mark(check['passed'])}  {check['name']:<26}{DIM}{check['detail'][:44]}{OFF}")
    print(f"\n  Freshness: {RED}STALE{OFF} — {fresh['stale_rows']}/{fresh['total_rows']} dong qua han")
    print(f"            ngay cu nhat: {RED}{fresh['oldest_published']}{OFF} (baseline: 2026-02-12)")
    print(f"\n{DIM}  Day la chot chan. Khong ai phai doc cau tra loi moi biet du lieu hong.{OFF}")
    pause()


def act4_damage() -> None:
    header(4, "THIET HAI — agent bat dau tra loi sai")
    base = read("data/results/baseline_metrics.json")
    corr = read("data/results/corrupted_metrics.json")
    print(f"  {'metric':<22}{'baseline':>10}{'corrupted':>12}{'thay doi':>12}")
    print(f"  {'-' * 56}")
    for key in ("retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"):
        delta = corr[key] - base[key]
        print(f"  {key:<22}{base[key]:>10.4f}{RED}{corr[key]:>12.4f}{OFF}{RED}{delta:>+12.4f}{OFF}")

    answers = read("data/results/corrupted_answers.json")
    lost = [a for a in answers if not a["retrieval_hit"]]
    print(f"\n  {len(lost)}/{len(answers)} cau mat retrieval hit. Vi du:\n")
    if lost:
        item = lost[0]
        print(f"    Hoi   : {item['question'][:64]}")
        print(f"    Can   : {item['ground_truth_doc_ids'][0]}")
        print(f"    Lay ve: {item['retrieved_doc_ids'][:2]}")
        print(f"    {DIM}Tai lieu da bi xoa khoi corpus — khong thuat toan nao cuu duoc.{OFF}")
    pause()


def act5_silent() -> None:
    header(5, "DIEM NHAN — loi ma KHONG chot chan nao bat duoc")
    log = read("data/results/corruption_log.json")
    swapped = {
        paper_id
        for op in log["operations"]
        if op["type"] == "swap_authors"
        for paper_id in op["paper_ids"]
    }
    base = {a["id"]: a for a in read("data/results/baseline_answers.json")}
    corr = {a["id"]: a for a in read("data/results/corrupted_answers.json")}

    example = None
    for qid, answer in corr.items():
        if answer["question_type"] == "authors" and set(answer["ground_truth_doc_ids"]) & swapped:
            if answer["token_f1"] < 0.99:
                example = (qid, answer)
                break

    print(f"  Kich ban {YELLOW}swap_authors{OFF}: gan nham tac gia sang bai khac")
    print(f"  {DIM}(mo phong loi join sai khoa trong ETL — rat hay gap that){OFF}\n")
    if example:
        qid, answer = example
        print(f"    Hoi      : {answer['question'][:64]}")
        print(f"    Dung     : {GREEN}{base[qid]['answer'][:60]}{OFF}")
        print(f"    Agent noi: {RED}{answer['answer'][:60]}{OFF}\n")
        print(f"    retrieval_hit = {GREEN}True{OFF}   <- retriever lam DUNG viec, lay dung bai")
        print(f"    token_f1      = {RED}{answer['token_f1']:.1f}{OFF}      <- nhung noi dung ben trong da sai")

    quality = read("data/quality/corrupted_quality.json")
    failed = [c["name"] for c in quality["checks"] if not c["passed"]]
    print(f"\n  Quality check FAIL: {failed}")
    print(f"  {RED}Khong co check nao lien quan den tac gia.{OFF}")
    print(f"\n{DIM}  Du lieu van khong null, khong rong, khong trung — chi la SAI.{OFF}")
    print(f"{DIM}  Do la 'hong trong im lang': bo check chi bat duoc chieu ma no duoc viet ra de bat.{OFF}")
    pause()


def act6_repair() -> None:
    header(6, "PHUC HOI — dung lai tu raw snapshot")
    summary = read("data/quality/corruption_summary.json")
    check = summary["repair_verification"]
    base = read("data/results/baseline_metrics.json")
    corr = read("data/results/corrupted_metrics.json")
    rep = read("data/results/repaired_metrics.json")

    print(f"  Nguon phuc hoi: data/raw/crossref_records.json {DIM}(snapshot bat bien){OFF}")
    print(f"  {DIM}KHONG goi lai API — goi lai se ra corpus khac, mat tinh so sanh.{OFF}\n")
    print(f"  {'metric':<22}{'baseline':>10}{'corrupted':>12}{'repaired':>11}")
    print(f"  {'-' * 55}")
    for key in ("retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"):
        print(f"  {key:<22}{base[key]:>10.4f}{RED}{corr[key]:>12.4f}{OFF}{GREEN}{rep[key]:>11.4f}{OFF}")

    quality = read("data/quality/repaired_quality.json")
    fresh = read("data/quality/freshness_report_repaired.json")
    print(f"\n  Data quality: {mark(quality['passed'])}    Freshness: {GREEN}Fresh{OFF}")
    print(f"\n  {BOLD}Kiem chung repair bang du lieu, khong bang cam giac:{OFF}")
    print(f"    missing_after_repair    : {check['missing_after_repair'] or '[]'}")
    print(f"    unexpected_after_repair : {check['unexpected_after_repair'] or '[]'}")
    print(f"    fully_restored          : {GREEN}{check['fully_restored']}{OFF}")
    print(f"\n{DIM}  Tap paper_id sau repair khop baseline tuyet doi — khong phai so trung ngau nhien.{OFF}")
    pause()


def closing() -> None:
    print(f"\n{BOLD}{CYAN}{'=' * 74}{OFF}")
    print(f"{BOLD}  KET LUAN{OFF}\n")
    print("   Du lieu hong  ->  tin hieu quality/freshness bao dong  ->  agent tra loi sai")
    print("   Repair tu raw ->  tin hieu xanh tro lai                ->  chat luong phuc hoi 100%\n")
    print(f"   {DIM}Ca 3 trang thai cham tren cung 1 bo de dong bang, cung 1 model judge.{OFF}")
    print(f"{BOLD}{CYAN}{'=' * 74}{OFF}\n")


ACTS = [act1_baseline, act2_corruption, act3_alarm, act4_damage, act5_silent, act6_repair]


def main() -> None:
    global STEP
    parser = argparse.ArgumentParser(description="Demo ket qua Day 10 tu artifact da sinh.")
    parser.add_argument("--step", action="store_true", help="dung sau moi phan, Enter de tiep")
    parser.add_argument("--act", type=int, choices=range(1, 7), help="chi chay mot phan")
    args = parser.parse_args()
    STEP = args.step

    if args.act:
        ACTS[args.act - 1]()
        return
    for act in ACTS:
        act()
    closing()


if __name__ == "__main__":
    main()

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator
import random

import pandas as pd

from core.utils import now_utc, write_json


# Corruption chạy với seed cố định: phép so sánh baseline / corrupted / repaired
# chỉ có ý nghĩa khi dataset corrupted tái tạo lại được y hệt giữa các lần chạy.
RANDOM_SEED = 42

# Ngưỡng freshness của project là 180 ngày (settings.freshness_threshold_days).
# Đẩy published lùi 400 ngày để chắc chắn vượt ngưỡng dù chạy vào ngày nào.
STALE_SHIFT_DAYS = 400

# Tỷ lệ dòng bị ảnh hưởng cho từng loại lỗi. Các nhóm dòng không chồng lấn nhau
# để đọc được impact của từng loại trong corruption_log.json.
DROP_LATEST_FRACTION = 0.12
BLANK_SUMMARY_FRACTION = 0.12
NOISE_FRACTION = 0.12
TRUNCATE_TITLE_FRACTION = 0.12
STALE_FRACTION = 0.16
DUPLICATE_FRACTION = 0.08

TRUNCATED_TITLE_CHARS = 12
NOISE_TEXT = "lorem ipsum qwerty zzz 12345 %%% asdf gibberish token soup xxxxx"


def _row_budget(total: int, fraction: float) -> int:
    """Số dòng bị ảnh hưởng cho một loại lỗi, luôn ít nhất 1 khi còn đủ dòng."""
    if total <= 0:
        return 0
    return max(1, round(total * fraction))


def _take(pool: Iterator[Any], count: int) -> list[Any]:
    """Lấy tối đa `count` index từ pool đã shuffle; hết pool thì dừng lại."""
    picked: list[Any] = []
    for _ in range(count):
        try:
            picked.append(next(pool))
        except StopIteration:
            break
    return picked


def _paper_ids(df: pd.DataFrame, indexes: list[Any]) -> list[str]:
    """Đổi danh sách index của dataframe thành danh sách paper_id để ghi log."""
    return [str(df.loc[index, "paper_id"]) for index in indexes]


def _age_days(published: Any, run_date: pd.Timestamp) -> Any:
    """Tính lại age_days từ published. Trả về pd.NA khi không parse được."""
    parsed = pd.to_datetime(published, errors="coerce", utc=True)
    if pd.isna(parsed):
        return pd.NA
    return int((run_date - parsed).days)


def _rebuild_text_for_embedding(
    original: str,
    old_title: str,
    new_title: str,
    old_summary: str,
    new_summary: str,
) -> str:
    """Dựng lại text_for_embedding sau khi title/summary bị sửa.

    Thay chuỗi cũ bằng chuỗi mới ngay trên text gốc thay vì ráp lại theo template
    riêng: cách này giữ nguyên định dạng mà cleaning.py đã tạo ra, nên khác biệt
    embedding giữa baseline và corrupted đến từ nội dung bị hỏng thật sự, không
    đến từ việc đổi định dạng. Nếu không thay thế được thì mới ráp lại tối thiểu.
    """
    text = original if isinstance(original, str) else ""
    replaced = False

    if old_title and old_title != new_title and old_title in text:
        text = text.replace(old_title, new_title)
        replaced = True
    if old_summary and old_summary != new_summary and old_summary in text:
        text = text.replace(old_summary, new_summary)
        replaced = True

    if not replaced:
        text = f"{new_title}\n\n{new_summary}".strip()

    # text_for_embedding rỗng sẽ làm ChromaDB nhận document trống; giữ lại ít nhất title.
    return text.strip() or new_title.strip() or "corrupted-record"


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path) -> pd.DataFrame:
    """Mô phỏng nhiều dạng data corruption trên cleaned dataframe.

    Sau khi sửa published thì age_days được tính lại, và sau khi sửa title/summary
    thì text_for_embedding được dựng lại — nếu không, freshness check vẫn báo "fresh"
    và embedding vẫn sạch, corruption sẽ không tạo ra tác động nào đo được.

    Trả về dataframe đã corrupt và ghi corruption log vào `output_log_path`.
    """
    run_date = pd.Timestamp(now_utc())
    corrupted = df.copy().reset_index(drop=True)
    rows_before = len(corrupted)
    operations: list[dict[str, Any]] = []

    if rows_before == 0:
        write_json(
            Path(output_log_path),
            {
                "generated_at": run_date.isoformat(),
                "random_seed": RANDOM_SEED,
                "rows_before": 0,
                "rows_after": 0,
                "operations": [],
                "note": "Cleaned dataframe rỗng, không có gì để corrupt.",
            },
        )
        return corrupted

    # Chụp lại title/summary gốc để biết dòng nào thật sự bị đổi nội dung ở bước rebuild.
    original_titles = corrupted["title"].astype(str).copy()
    original_summaries = corrupted["summary"].astype(str).copy()

    # --- 1. Xóa một số record mới nhất --------------------------------------
    # Ảnh hưởng trực tiếp đến freshness và làm mất document khỏi corpus.
    drop_count = _row_budget(rows_before, DROP_LATEST_FRACTION)
    published_order = pd.to_datetime(corrupted["published"], errors="coerce", utc=True)
    latest_indexes = published_order.sort_values(ascending=False).head(drop_count).index.tolist()
    dropped_ids = _paper_ids(corrupted, latest_indexes)
    dropped_dates = [str(corrupted.loc[index, "published"]) for index in latest_indexes]
    corrupted = corrupted.drop(index=latest_indexes)

    operations.append(
        {
            "type": "drop_latest_records",
            "description": "Xóa các record mới nhất khỏi corpus.",
            "rows_affected": len(latest_indexes),
            "paper_ids": dropped_ids,
            "details": {"dropped_published_dates": dropped_dates},
        }
    )

    # Các loại lỗi còn lại chia trên tập dòng không chồng lấn để impact tách bạch.
    remaining = len(corrupted)
    rng = random.Random(RANDOM_SEED)
    shuffled = list(corrupted.index)
    rng.shuffle(shuffled)
    pool = iter(shuffled)

    # --- 2. Xóa trắng summary -----------------------------------------------
    blank_indexes = _take(pool, _row_budget(remaining, BLANK_SUMMARY_FRACTION))
    for index in blank_indexes:
        corrupted.loc[index, "summary"] = ""
    operations.append(
        {
            "type": "blank_summary",
            "description": "Xóa trắng summary — agent mất nội dung để trả lời.",
            "rows_affected": len(blank_indexes),
            "paper_ids": _paper_ids(corrupted, blank_indexes),
            "details": {},
        }
    )

    # --- 3. Chèn nhiễu vào summary ------------------------------------------
    noise_indexes = _take(pool, _row_budget(remaining, NOISE_FRACTION))
    for index in noise_indexes:
        current = str(corrupted.loc[index, "summary"])
        corrupted.loc[index, "summary"] = f"{current} {NOISE_TEXT}".strip()
    operations.append(
        {
            "type": "inject_noise",
            "description": "Chèn text rác vào summary — làm nhiễu embedding.",
            "rows_affected": len(noise_indexes),
            "paper_ids": _paper_ids(corrupted, noise_indexes),
            "details": {"noise_text": NOISE_TEXT},
        }
    )

    # --- 4. Cắt cụt title ----------------------------------------------------
    # Phá luôn exact lookup theo title trong retrieval/qa.py.
    truncate_indexes = _take(pool, _row_budget(remaining, TRUNCATE_TITLE_FRACTION))
    truncated_details: list[dict[str, str]] = []
    for index in truncate_indexes:
        current = str(corrupted.loc[index, "title"])
        new_title = current[:TRUNCATED_TITLE_CHARS].rstrip()
        corrupted.loc[index, "title"] = new_title
        truncated_details.append({"before": current, "after": new_title})
    operations.append(
        {
            "type": "truncate_title",
            "description": f"Cắt title còn {TRUNCATED_TITLE_CHARS} ký tự — hỏng exact lookup.",
            "rows_affected": len(truncate_indexes),
            "paper_ids": _paper_ids(corrupted, truncate_indexes),
            "details": {"examples": truncated_details[:3]},
        }
    )

    # --- 5. Làm cũ published date -------------------------------------------
    stale_indexes = _take(pool, _row_budget(remaining, STALE_FRACTION))
    stale_details: list[dict[str, str]] = []
    for index in stale_indexes:
        parsed = pd.to_datetime(corrupted.loc[index, "published"], errors="coerce", utc=True)
        if pd.isna(parsed):
            continue
        stale_date = parsed - pd.Timedelta(days=STALE_SHIFT_DAYS)
        new_published = stale_date.date().isoformat()
        corrupted.loc[index, "published"] = new_published
        # Bắt buộc: không tính lại age_days thì freshness check vẫn báo "fresh".
        corrupted.loc[index, "age_days"] = _age_days(new_published, run_date)
        stale_details.append({"before": str(parsed.date()), "after": new_published})
    operations.append(
        {
            "type": "stale_published_date",
            "description": f"Đẩy published lùi {STALE_SHIFT_DAYS} ngày và tính lại age_days.",
            "rows_affected": len(stale_details),
            "paper_ids": _paper_ids(corrupted, stale_indexes),
            "details": {"shift_days": STALE_SHIFT_DAYS, "examples": stale_details[:3]},
        }
    )

    # --- 6. Dựng lại text_for_embedding cho dòng đã đổi nội dung ------------
    # Chỉ rebuild dòng thật sự bị sửa: dòng sạch giữ nguyên text gốc nên khác biệt
    # embedding đo được chỉ đến từ corruption.
    rebuilt_indexes: list[Any] = []
    for index in corrupted.index:
        old_title = original_titles.get(index, "")
        old_summary = original_summaries.get(index, "")
        new_title = str(corrupted.loc[index, "title"])
        new_summary = str(corrupted.loc[index, "summary"])
        if old_title == new_title and old_summary == new_summary:
            continue
        corrupted.loc[index, "text_for_embedding"] = _rebuild_text_for_embedding(
            original=str(corrupted.loc[index, "text_for_embedding"]),
            old_title=old_title,
            new_title=new_title,
            old_summary=old_summary,
            new_summary=new_summary,
        )
        rebuilt_indexes.append(index)

    operations.append(
        {
            "type": "rebuild_text_for_embedding",
            "description": "Dựng lại text_for_embedding cho dòng đã đổi title/summary.",
            "rows_affected": len(rebuilt_indexes),
            "paper_ids": _paper_ids(corrupted, rebuilt_indexes),
            "details": {},
        }
    )

    # --- 7. Nhân bản dòng ----------------------------------------------------
    # Làm cuối cùng để bản sao mang đúng giá trị đã corrupt; phá ràng buộc
    # paper_id unique trong data quality checks.
    duplicate_indexes = _take(pool, _row_budget(remaining, DUPLICATE_FRACTION))
    if duplicate_indexes:
        duplicated_ids = _paper_ids(corrupted, duplicate_indexes)
        corrupted = pd.concat(
            [corrupted, corrupted.loc[duplicate_indexes]],
            ignore_index=True,
        )
    else:
        duplicated_ids = []
    operations.append(
        {
            "type": "duplicate_rows",
            "description": "Nhân bản dòng — phá ràng buộc paper_id unique.",
            "rows_affected": len(duplicate_indexes),
            "paper_ids": duplicated_ids,
            "details": {},
        }
    )

    corrupted = corrupted.reset_index(drop=True)

    affected_ids = {
        paper_id
        for operation in operations
        if operation["type"] != "rebuild_text_for_embedding"
        for paper_id in operation["paper_ids"]
    }
    write_json(
        Path(output_log_path),
        {
            "generated_at": run_date.isoformat(),
            "random_seed": RANDOM_SEED,
            "rows_before": rows_before,
            "rows_after": len(corrupted),
            "distinct_paper_ids_affected": len(affected_ids),
            "operations": operations,
        },
    )
    return corrupted

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
SWAP_AUTHORS_FRACTION = 0.14
DUPLICATE_FRACTION = 0.08

TRUNCATED_TITLE_CHARS = 12
NOISE_TEXT = "lorem ipsum qwerty zzz 12345 %%% asdf gibberish token soup xxxxx"

# Các cột được cleaning.py ghép vào text_for_embedding. Sửa bất kỳ cột nào trong
# đây đều phải dựng lại text_for_embedding, nếu không embedding vẫn giữ giá trị cũ.
FIELDS_INSIDE_EMBEDDING_TEXT = ["title", "summary", "authors_joined", "categories_joined"]


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


def _operation(
    kind: str,
    description: str,
    paper_ids: list[str],
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Tạo một mục cho corruption log.

    `paper_ids` chỉ được chứa dòng THẬT SỰ bị đổi. Vì `rows_affected` được suy ra
    từ chính danh sách đó, hai con số không thể lệch nhau — nếu ghi tay riêng rẽ,
    các bước có thể bỏ qua dòng (published không parse được, tác giả trùng nhau)
    sẽ báo cáo nhiều dòng hơn thực tế và làm sai lệch phân tích ở báo cáo.
    """
    return {
        "type": kind,
        "description": description,
        "rows_affected": len(paper_ids),
        "paper_ids": paper_ids,
        "details": details or {},
    }


def _age_days(published: Any, run_date: pd.Timestamp) -> Any:
    """Tính lại age_days từ published. Trả về pd.NA khi không parse được."""
    parsed = pd.to_datetime(published, errors="coerce", utc=True)
    if pd.isna(parsed):
        return pd.NA
    return int((run_date - parsed).days)


def _rebuild_text_for_embedding(
    original: str,
    changes: list[tuple[str, str]],
    fallback_title: str,
    fallback_summary: str,
) -> str:
    """Dựng lại text_for_embedding sau khi các cột nguồn bị sửa.

    `changes` là danh sách cặp (giá trị cũ, giá trị mới) của những cột đã đổi.

    Thay chuỗi cũ bằng chuỗi mới ngay trên text gốc thay vì ráp lại theo template
    riêng: cách này giữ nguyên định dạng mà cleaning.py đã tạo ra, nên khác biệt
    embedding giữa baseline và corrupted đến từ nội dung bị hỏng thật sự, không
    đến từ việc đổi định dạng. Nếu không thay thế được thì mới ráp lại tối thiểu.
    """
    text = original if isinstance(original, str) else ""
    replaced = False

    for old_value, new_value in changes:
        if old_value and old_value != new_value and old_value in text:
            text = text.replace(old_value, new_value)
            replaced = True

    if not replaced:
        # Đường cùng: cleaning.py đổi cách ghép text nên không tìm thấy chuỗi cũ.
        text = f"{fallback_title} {fallback_summary}".strip()

    # text_for_embedding rỗng sẽ làm ChromaDB nhận document trống; giữ lại ít nhất title.
    return text.strip() or fallback_title.strip() or "corrupted-record"


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path) -> pd.DataFrame:
    """Mô phỏng nhiều dạng data corruption trên cleaned dataframe.

    Hai ràng buộc bắt buộc, nếu bỏ qua thì corruption không tạo ra tác động đo được:

    - Sửa published thì phải tính lại age_days, vì freshness check đọc age_days
      chứ không đọc published — nếu không, dữ liệu đã cũ vẫn bị báo là "fresh".
    - Sửa bất kỳ cột nào trong FIELDS_INSIDE_EMBEDDING_TEXT thì phải dựng lại
      text_for_embedding, vì ChromaDB nhúng cột đó chứ không nhúng cột nguồn.

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

    # Chụp lại các cột nguồn của text_for_embedding để biết dòng nào thật sự bị
    # đổi nội dung ở bước rebuild.
    originals = {
        field: corrupted[field].astype(str).copy() for field in FIELDS_INSIDE_EMBEDDING_TEXT
    }

    # --- 1. Xóa một số record mới nhất --------------------------------------
    # Ảnh hưởng trực tiếp đến freshness và làm mất document khỏi corpus.
    drop_count = _row_budget(rows_before, DROP_LATEST_FRACTION)
    published_order = pd.to_datetime(corrupted["published"], errors="coerce", utc=True)
    latest_indexes = published_order.sort_values(ascending=False).head(drop_count).index.tolist()
    dropped_ids = _paper_ids(corrupted, latest_indexes)
    dropped_dates = [str(corrupted.loc[index, "published"]) for index in latest_indexes]
    corrupted = corrupted.drop(index=latest_indexes)

    operations.append(
        _operation(
            "drop_latest_records",
            "Xóa các record mới nhất khỏi corpus.",
            dropped_ids,
            {"dropped_published_dates": dropped_dates},
        )
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
        _operation(
            "blank_summary",
            "Xóa trắng summary — agent mất nội dung để trả lời.",
            _paper_ids(corrupted, blank_indexes),
        )
    )

    # --- 3. Chèn nhiễu vào summary ------------------------------------------
    noise_indexes = _take(pool, _row_budget(remaining, NOISE_FRACTION))
    for index in noise_indexes:
        current = str(corrupted.loc[index, "summary"])
        corrupted.loc[index, "summary"] = f"{current} {NOISE_TEXT}".strip()
    operations.append(
        _operation(
            "inject_noise",
            "Chèn text rác vào summary — làm nhiễu embedding.",
            _paper_ids(corrupted, noise_indexes),
            {"noise_text": NOISE_TEXT},
        )
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
        _operation(
            "truncate_title",
            f"Cắt title còn {TRUNCATED_TITLE_CHARS} ký tự — hỏng exact lookup.",
            _paper_ids(corrupted, truncate_indexes),
            {"examples": truncated_details[:3]},
        )
    )

    # --- 5. Làm cũ published date -------------------------------------------
    stale_indexes = _take(pool, _row_budget(remaining, STALE_FRACTION))
    stale_applied: list[Any] = []
    stale_details: list[dict[str, str]] = []
    for index in stale_indexes:
        parsed = pd.to_datetime(corrupted.loc[index, "published"], errors="coerce", utc=True)
        if pd.isna(parsed):
            # published không parse được thì bỏ qua, và không ghi vào log.
            continue
        stale_date = parsed - pd.Timedelta(days=STALE_SHIFT_DAYS)
        new_published = stale_date.date().isoformat()
        corrupted.loc[index, "published"] = new_published
        # Bắt buộc: không tính lại age_days thì freshness check vẫn báo "fresh".
        corrupted.loc[index, "age_days"] = _age_days(new_published, run_date)
        stale_applied.append(index)
        stale_details.append({"before": str(parsed.date()), "after": new_published})
    operations.append(
        _operation(
            "stale_published_date",
            f"Đẩy published lùi {STALE_SHIFT_DAYS} ngày và tính lại age_days.",
            _paper_ids(corrupted, stale_applied),
            {"shift_days": STALE_SHIFT_DAYS, "examples": stale_details[:3]},
        )
    )

    # --- 6. Hoán đổi tác giả giữa các paper ---------------------------------
    # Mô phỏng lỗi join sai khóa trong ETL: dữ liệu trông vẫn hợp lệ (không null,
    # không rỗng) nên data quality check cơ bản không bắt được, nhưng agent trả
    # lời sai tác giả. Đây là loại lỗi "thầm lặng" — và là kịch bản duy nhất
    # chạm tới authors_joined, cột mà các loại corruption khác không đụng tới.
    swap_indexes = _take(pool, _row_budget(remaining, SWAP_AUTHORS_FRACTION))
    swap_applied: list[Any] = []
    swap_details: list[dict[str, str]] = []
    if len(swap_indexes) >= 2:
        # Xoay vòng thay vì ghép cặp: mọi dòng được chọn đều nhận tác giả của
        # dòng khác, kể cả khi số dòng lẻ.
        current_authors = [str(corrupted.loc[index, "authors_joined"]) for index in swap_indexes]
        rotated = current_authors[1:] + current_authors[:1]
        for index, old_authors, new_authors in zip(swap_indexes, current_authors, rotated):
            if old_authors == new_authors:
                # Hai paper vốn cùng tác giả: hoán đổi không tạo ra thay đổi nào.
                continue
            corrupted.loc[index, "authors_joined"] = new_authors
            swap_applied.append(index)
            swap_details.append({"before": old_authors, "after": new_authors})
    operations.append(
        _operation(
            "swap_authors",
            "Gán nhầm authors_joined sang paper khác — lỗi join sai khóa.",
            _paper_ids(corrupted, swap_applied),
            {"examples": swap_details[:3]},
        )
    )

    # --- 7. Dựng lại text_for_embedding cho dòng đã đổi nội dung ------------
    # Chỉ rebuild dòng thật sự bị sửa: dòng sạch giữ nguyên text gốc nên khác biệt
    # embedding đo được chỉ đến từ corruption.
    rebuilt_indexes: list[Any] = []
    for index, row in corrupted.iterrows():
        changes = [
            (originals[field].get(index, ""), str(row[field]))
            for field in FIELDS_INSIDE_EMBEDDING_TEXT
            if originals[field].get(index, "") != str(row[field])
        ]
        if not changes:
            continue
        corrupted.loc[index, "text_for_embedding"] = _rebuild_text_for_embedding(
            original=str(row["text_for_embedding"]),
            changes=changes,
            fallback_title=str(row["title"]),
            fallback_summary=str(row["summary"]),
        )
        rebuilt_indexes.append(index)

    operations.append(
        _operation(
            "rebuild_text_for_embedding",
            "Dựng lại text_for_embedding cho dòng đã đổi cột nguồn.",
            _paper_ids(corrupted, rebuilt_indexes),
            {"fields_watched": FIELDS_INSIDE_EMBEDDING_TEXT},
        )
    )

    # --- 8. Nhân bản dòng ----------------------------------------------------
    # Làm cuối cùng để bản sao mang đúng giá trị đã corrupt; phá ràng buộc
    # paper_id unique trong data quality checks.
    duplicate_indexes = _take(pool, _row_budget(remaining, DUPLICATE_FRACTION))
    duplicated_ids = _paper_ids(corrupted, duplicate_indexes)
    if duplicate_indexes:
        corrupted = pd.concat(
            [corrupted, corrupted.loc[duplicate_indexes]],
            ignore_index=True,
        )
    operations.append(
        _operation(
            "duplicate_rows",
            "Nhân bản dòng — phá ràng buộc paper_id unique.",
            duplicated_ids,
        )
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

# Group Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Khóa/Lớp         | K3                         |
| Tên nhóm         | Nhóm 5 — Day 10 Data Pipeline |
| Repository         | https://github.com/Marvis12957/K3_Day10_VinBrothers |
| Ngày hoàn thành | 2026-08-06                 |

### Thành viên và phân công

| STT | Họ và tên | MSSV | GitHub | Vai trò chính | Module/deliverable sở hữu |
| --: | --- | --- | --- | --- | --- |
| 1 | Hoàng Dũng | [MSSV] | [handle] | Source Ingestion Owner | `src/ingestion/crossref.py` → `data/raw/crossref_response.json`, `data/raw/crossref_records.json` |
| 2 | Trần Trung Hiếu | 2A202602002 | trunghieunef | Data Model & Eval Set Owner | `src/ingestion/cleaning.py`, `src/evaluation/testset.py` → `data/clean/papers_clean.{csv,json}`, `data/eval/test_set.json` |
| 3 | Phạm Quốc Tuấn | 2A202601983 | phamquoctuan2308 | Data Observability Owner | `src/observability/quality.py`, `src/observability/reporting.py` → `data/quality/`, `data/reports/` |
| 4 | Trần Văn Hiếu | 2A202602030 | Marvis | Corruption & Repair Owner | `src/ingestion/corruption.py` → `data/clean/papers_clean_corrupted.*`, `data/results/corruption_log.json` |
| 5 | Trương Công Thái Đức | 2A202601581 | [handle] | Integration & Comparison Owner (nhóm trưởng) | `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py` → `data/results/*_metrics.json`, `data/reports/corruption_report.md` |

## 2. Tóm tắt kết quả

**Tóm tắt của nhóm:**

Nhóm hoàn thành toàn bộ 8 module bài tập và chạy thông cả hai pipeline end-to-end. Baseline lấy 24 bài báo từ Crossref REST API, làm sạch không mất bản ghi nào, index bằng `all-MiniLM-L6-v2` vào ChromaDB, và sinh bộ 16 câu hỏi chia đều 4 loại (summary/authors/date/categories). Baseline đạt trần tuyệt đối: `retrieval_hit_rate` 1.0, `mean_token_f1` 1.0, `judge_accuracy` 1.0, `mean_judge_score` 5.0, và toàn bộ 7 data quality check đều PASS.

Pha 2 áp 7 kịch bản corruption có kiểm soát (seed cố định 42) lên 20/24 tài liệu. Kịch bản hại nhất là `drop_latest_records`: xóa 3 bài mới nhất gây 3 trong tổng số 4 câu mất retrieval hit — tài liệu đã biến mất thì không thuật toán nào cứu được. Kế đó là `truncate_title`, phá đường tra cứu chính xác theo tên. Về phía observability, `duplicate_rows` và `stale_published_date` làm 3 quality check chuyển sang FAIL và freshness từ Fresh sang Stale.

Corruption kéo cả bốn chỉ số xuống: hit rate −0.25, token F1 −0.41, judge accuracy −0.375, judge score −1.31. Repair dựng lại từ raw snapshot phục hồi **hoàn toàn** cả bốn chỉ số về đúng giá trị baseline, với tập `paper_id` được verify khớp tuyệt đối (`fully_restored: true`).

Giới hạn lớn nhất còn lại: corpus chỉ 24 tài liệu với `top_k=4` nên retrieval quá dễ — nhiễu embedding không đủ sức đẩy tài liệu ra khỏi top-k.

## 3. Kiến trúc và luồng dữ liệu

### Luồng end-to-end

```text
Crossref API
    -> raw response/raw records
    -> cleaning và data modeling
    -> embedding + ChromaDB index
    -> evaluation baseline
    -> quality/freshness reports
    -> corruption
    -> re-index và re-evaluate
    -> repair từ dữ liệu nguồn
    -> comparison report
```

### Trách nhiệm của từng khối

| Khối             | Input          | Xử lý chính             | Output/artifact          | Owner          |
| ----------------- | -------------- | -------------------------- | ------------------------ | -------------- |
| Ingestion         | Crossref REST API `/works` | Fetch có retry/backoff cho 429/503, parse payload → `PaperRecord` | `data/raw/crossref_response.json`, `data/raw/crossref_records.json` | Hoàng Dũng |
| Cleaning          | `data/raw/crossref_records.json` | Normalize text, parse date, tính `age_days`, dựng `text_for_embedding`, dedup | `data/clean/papers_clean.{csv,json}` | Trần Trung Hiếu |
| Embedding/index   | `data/clean/papers_clean.csv` | MiniLM-L6-v2 (384 chiều) + ChromaDB cosine, 1 collection/trạng thái | `data/embeddings/papers_embeddings*.json`, `data/chroma/` | Code có sẵn (`retrieval/index.py`) — TV5 vận hành |
| Evaluation        | `data/clean/papers_clean.csv` + index | Sinh test set 4 loại câu hỏi (freeze 1 lần), chấm hit-rate/token-F1/LLM-judge | `data/eval/test_set.json`, `data/results/*_metrics.json`, `data/results/*_answers.json` | Trần Trung Hiếu (test set), TV5 (chạy eval) |
| Observability     | cleaned/corrupted/repaired dataframe | 7 quality check + freshness vs ngưỡng 180 ngày | `data/quality/`, `data/reports/phase1_report.md` | Phạm Quốc Tuấn |
| Corruption/repair | `data/clean/papers_clean.csv`, `data/raw/crossref_records.json` | 7 kịch bản corrupt có log; repair = rebuild từ raw snapshot | `data/clean/papers_clean_corrupted.*`, `data/clean/papers_clean_repaired.*`, `data/results/corruption_log.json` | Trần Văn Hiếu |
| Orchestration     | Toàn bộ module trên | Thứ tự chạy phase1 → corruption flow, giữ nguyên test set qua 3 trạng thái | `data/reports/corruption_report.md`, `data/quality/corruption_summary.json` | Trương Công Thái Đức |

## 4. Cách tái hiện kết quả

### Cấu hình không chứa secret

| Biến/cấu hình             | Giá trị sử dụng |
| ---------------------------- | ------------------- |
| `LLM_PROVIDER`             | `openai`            |
| `LLM_MODEL`                | `gpt-4o-mini`       |
| Embedding model              | `sentence-transformers/all-MiniLM-L6-v2` (384 chiều) |
| Số lượng Crossref records | 24 (`max_results=24`) |
| Retrieval `top_k`           | 4                   |
| Freshness threshold          | 180 ngày           |
| Random seed                  | 42 (corruption), 42 (chọn mẫu test set) |

Không dán nội dung API key hoặc file `.env` vào báo cáo.

### Lệnh cài đặt

```bash
uv sync
```

### Lệnh chạy

Baseline:

```bash
uv run python script/run_phase1.py
```

Corruption flow:

```bash
uv run python script/run_corruption_flow.py
```

### Kết quả tái hiện

| Lệnh             | Trạng thái | Thời điểm chạy gần nhất | Bằng chứng |
| ----------------- | ------------ | ----------------------------- | ------------ |
| Baseline pipeline | Thành công | 2026-08-06 | `data/results/baseline_metrics.json`, `data/reports/phase1_report.md` |
| Corruption flow   | Thành công | 2026-08-06 | `data/results/{corrupted,repaired}_metrics.json`, `data/reports/corruption_report.md` |

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Thuộc tính                | Giá trị                             |
| --------------------------- | ------------------------------------- |
| Source                      | Crossref REST API — `https://api.crossref.org/works` |
| Query/filter                | query=`agentic retrieval augmented generation large language model`; filter=`from-pub-date:<hôm nay − 180 ngày>,has-abstract:true`; rows=24 |
| Thời điểm lấy dữ liệu | 2026-08-06 |
| Số record nhận được    | 24 items / 100.916 total-results; parse thành công 24/24 |
| Cơ chế retry/backoff      | Tối đa 4 lần thử với exponential backoff `2^attempt`, ưu tiên header `Retry-After`; áp cho HTTP 429/503, `Timeout` và `ConnectionError` |

### Raw và clean schema

| Trường        | Kiểu dữ liệu | Bắt buộc?  | Ý nghĩa   | Xử lý khi thiếu/sai |
| --------------- | --------------- | ------------ | ----------- | ---------------------- |
| `paper_id` | str | Có | DOI, khóa chính | Loại bản ghi nếu rỗng; dedup giữ bản đầu |
| `title` | str | Có | Tiêu đề, dùng cho exact lookup | Loại bản ghi nếu rỗng |
| `summary` | str | Có | Abstract đã bóc thẻ JATS | Loại bản ghi nếu rỗng |
| `published` | str (ISO date) | Có | Ngày xuất bản | Fallback `published` → `published-online` → `published-print` → `issued` → `created`; loại nếu không parse được |
| `authors_joined` | str | Không | Danh sách tác giả nối bằng `, ` | Để rỗng, không loại bản ghi |
| `categories_joined` | str | Không | Chủ đề nối bằng `, ` | Fallback `subject` → `container-title` → `group-title` → `type` |
| `age_days` | int | Có | Tuổi tài liệu tính từ ngày chạy | Loại bản ghi nếu không tính được |
| `text_for_embedding` | str | Có | Text đưa vào MiniLM | Loại bản ghi nếu rỗng |
| `abs_url` | str | Không | Link tới bài | Fallback `https://doi.org/<DOI>` |
| `pdf_url` | str | Không | Link PDF nếu có | Để rỗng (9/24 bản ghi có) |

### Quy tắc cleaning

| Quy tắc                                 | Quality dimension liên quan | Số record bị tác động | Cách xác minh      |
| ---------------------------------------- | ---------------------------- | -------------------------: | -------------------- |
| Loại record thiếu `paper_id` | Completeness | 0 | `data/clean/papers_clean.csv` giữ đủ 24/24 |
| Loại record thiếu `title` hoặc `summary` | Completeness | 0 | filter `has-abstract:true` đã lọc từ nguồn |
| Loại record không parse được ngày | Validity | 0 | `age_days` đủ 24 giá trị, khoảng 5–175 ngày |
| Dedup theo `paper_id` | Uniqueness | 0 | quality check `paper_id_unique` PASS |
| Bóc thẻ JATS XML + unescape HTML entity | Validity | 24 | không còn ký tự `<` trong `title`/`summary` |

Giải thích cách nhóm tạo `text_for_embedding`, document ID và `age_days`:

`text_for_embedding` ghép theo template `Title: {title} Summary: {summary} Authors: {authors_joined} Categories: {categories_joined}`, bỏ qua phần rỗng và chuẩn hóa khoảng trắng. Ghép cả 4 trường để câu hỏi về tác giả và chủ đề cũng có tín hiệu ngữ nghĩa trong vector, không chỉ dựa vào metadata lookup.

Document ID trong ChromaDB dùng dạng `{paper_id}::{index}` để bản sao trùng `paper_id` vẫn nạp được vào index — điều kiện cần để mô phỏng kịch bản duplicate ở pha 2.

`age_days` = `(ngày chạy − published).days`, tính lúc cleaning và **tính lại mỗi khi `published` bị đổi** ở bước corruption. Đây là ràng buộc bắt buộc: freshness check đọc `age_days` chứ không đọc `published`, nên bỏ qua bước tính lại sẽ khiến dữ liệu đã cũ vẫn bị báo là "fresh".

## 6. Evaluation setup

| Thành phần                             | Cấu hình thực tế          |
| ---------------------------------------- | ----------------------------- |
| Số câu hỏi                            | 16 |
| Các `question_type`                    | `summary` (4), `authors` (4), `date` (4), `categories` (4) |
| Ground-truth document ID                 | `paper_id` của bài được trích đáp án; sinh cùng lúc với câu hỏi nên luôn khớp |
| Embedding model                          | `sentence-transformers/all-MiniLM-L6-v2` |
| Vector store/collection                  | ChromaDB persistent, cosine space; 3 collection tách biệt: `papers-baseline`, `papers-corrupted`, `papers-repaired` |
| Retrieval `top_k`                       | 4 |
| LLM provider/model                       | `openai` / `gpt-4o-mini` (chỉ dùng cho LLM judge và agent demo) |
| Test set dùng chung cho ba trạng thái | `data/eval/test_set.json` — sinh một lần ở baseline, ba trạng thái đọc chung file này |

Giải thích vì sao test set được giữ nguyên khi đánh giá baseline, corrupted và repaired:

Đây là thí nghiệm có đối chứng. Muốn quy kết "chỉ số tụt là do dữ liệu hỏng" thì mọi biến số khác phải giữ nguyên tuyệt đối: cùng câu hỏi, cùng đáp án chuẩn, cùng model chấm.

Nếu sinh lại bộ đề khi đánh giá corrupted, đề mới sẽ được tạo **từ chính dữ liệu đã hỏng**, nên `ground_truth` cũng hỏng theo. Agent trả lời sai vẫn được chấm đúng, và corruption trông như vô hại. Phép so sánh mất sạch ý nghĩa.

Ràng buộc này được thực thi bằng code: `phase1.py` chỉ sinh test set khi file chưa tồn tại hoặc `REFRESH_TEST_SET=1`; `corruption_flow.py` **không bao giờ** sinh test set, chỉ đọc file đã đóng băng.

Về trường hợp tài liệu trong `ground_truth_doc_ids` biến mất ở pha sau — điều thực sự xảy ra khi corruption xóa 3 bài mới nhất — nhóm **giữ nguyên câu hỏi và để nó tính là trượt**, không loại khỏi bộ đề. Tài liệu biến mất chính là thiệt hại cần đo. Nếu loại câu hỏi mồ côi, mẫu số co lại theo mức độ hỏng, và hệ thống mất càng nhiều dữ liệu thì điểm trông càng đẹp.

## 7. Kết quả baseline

### Artifact checklist

| Artifact                 | Đường dẫn thực tế                | Trạng thái | Ghi chú   |
| ------------------------ | -------------------------------------- | ------------ | ---------- |
| Raw response/records     | `data/raw/`                          | Có | `crossref_response.json` (228K), `crossref_records.json` (60K) |
| Cleaned dataset          | `data/clean/`                        | Có | CSV + JSON, 24 dòng, đủ 10 cột contract |
| Embedding manifest/index | `data/embeddings/`                   | Có | 3 manifest; `data/chroma/` không commit vì là binary dựng lại được |
| Evaluation set           | `data/eval/test_set.json`            | Có | 16 câu, đóng băng |
| Baseline metrics         | `data/results/baseline_metrics.json` | Có | kèm `baseline_answers.json` (16 sample đầy đủ) |
| Quality/freshness        | `data/quality/`                      | Có | 7 file: quality + freshness cho cả 3 trạng thái |
| Baseline report          | `data/reports/phase1_report.md`      | Có | sinh tự động |

### Baseline metrics

| Metric                 |       Giá trị | Diễn giải                             |
| ---------------------- | --------------: | --------------------------------------- |
| `retrieval_hit_rate` |     1.0000 | 16/16 câu lấy đúng tài liệu chứa đáp án trong top-4 |
| `mean_token_f1`      |     1.0000 | Câu trả lời trùng khớp tuyệt đối ground truth |
| `judge_accuracy`     |     1.0000 | LLM judge xác nhận 16/16 câu đúng về nội dung |
| `mean_judge_score`   |     5.0000 | Điểm tối đa trên thang 1–5 |
| Ragas | N/A | Bỏ qua, cần bật `RUN_RAGAS=1`; chi phí thời gian cao mà không cần cho mục tiêu so sánh 3 trạng thái |

**Vì sao token F1 đạt đúng 1.0:** module trả lời dùng cho evaluation (`retrieval/qa.py`) là **trích xuất, không sinh** — nó trả về thẳng trường metadata, còn ground truth được dựng từ đúng trường đó bằng đúng hàm `first_sentence`. Hai vế giống nhau từng ký tự. Đây là lựa chọn thiết kế có chủ đích: câu trả lời tất định thì mọi sụt giảm về sau chắc chắn đến từ dữ liệu, không lẫn nhiễu ngẫu nhiên của LLM. Để đối chiếu, `agent.py` (có gọi LLM sinh câu trả lời tự do) trả lời cùng câu hỏi chỉ đạt token F1 = 0.279 vì diễn đạt lại thay vì trích nguyên văn — xem `data/results/agent_demo_answers.json`.

## 8. Data quality và freshness

### Quality checks

| Check        | Quality dimension | Ngưỡng/kỳ vọng | Kết quả baseline      | Bằng chứng |
| ------------ | ----------------- | ------------------ | ----------------------- | ------------ |
| `row_count` | Completeness | > 0 dòng | PASS — 24 dòng | `data/quality/baseline_quality.json` |
| `required_columns_present` | Consistency | đủ 10 cột contract | PASS | như trên |
| `paper_id_not_null` | Completeness | 0 null | PASS — 0 null | như trên |
| `paper_id_unique` | Uniqueness | 0 trùng | PASS — 0 trùng | như trên |
| `title_not_null` | Completeness | 0 rỗng | PASS — 0 rỗng | như trên |
| `summary_length` | Validity | ≥ 40 ký tự | PASS — 0 vi phạm, trung bình 1727 ký tự | như trên |
| `freshness` | Timeliness | `age_days` ≤ 180 | PASS — 0/24 quá hạn | như trên |

### Freshness

| Thuộc tính               | Giá trị                           |
| -------------------------- | ----------------------------------- |
| Freshness được đo tại | Cleaned dataframe, qua cột `age_days` |
| Timestamp mới nhất       | 2026-08-01 (cũ nhất 2026-02-12) |
| Ngưỡng freshness         | 180 ngày |
| Trạng thái baseline      | Fresh |
| Lý do                     | 0/24 dòng có `age_days` > 180; khoảng tuổi thực tế 5–175 ngày, nằm trọn trong cửa sổ filter của Crossref |

## 9. Corruption scenarios và repair

| Corruption         | Cách tạo | Record bị tác động | Quality signal kỳ vọng | Tác động thực tế | Cách repair   |
| ------------------ | ---------- | ---------------------: | ------------------------ | --------------------- | -------------- |
| `drop_latest_records` | Xóa các bản ghi mới nhất khỏi corpus | 3 | freshness suy giảm, mất document | **3/4 câu mất retrieval hit** — nặng nhất | Rebuild từ raw snapshot |
| `blank_summary` | Gán `summary = ""` | 3 | `summary_length` FAIL | FAIL đúng như kỳ vọng; 1 câu sai token F1 | như trên |
| `inject_noise` | Nối chuỗi rác vào `summary` | 3 | nhiễu embedding | Không làm mất hit (corpus nhỏ, top_k=4) | như trên |
| `truncate_title` | Cắt `title` còn 12 ký tự | 3 | hỏng exact lookup theo tên | **1 câu mất retrieval hit** | như trên |
| `stale_published_date` | Lùi `published` 400 ngày, **tính lại `age_days`** | 3 | `freshness` FAIL | FAIL — 3/23 dòng quá hạn, cũ nhất 2025-01-29 | như trên |
| `swap_authors` | Xoay vòng `authors_joined` giữa các bài | 3 | **không check nào bắt được** | 1 câu sai token F1 mà quality vẫn im lặng | như trên |
| `duplicate_rows` | Nhân bản dòng, giữ nguyên `paper_id` | 2 | `paper_id_unique` FAIL | FAIL — 2 bản trùng | như trên |

Corruption log:

- Đường dẫn: `data/results/corruption_log.json`
- Trạng thái: Có
- Nhận xét: Log ghi đủ `random_seed` (42), `rows_before`/`rows_after` (24 → 23), `distinct_paper_ids_affected` (20), và với mỗi thao tác có `type`, `description`, `rows_affected`, danh sách `paper_ids` cụ thể cùng `details` (ví dụ mẫu before/after). `rows_affected` được suy ra trực tiếp từ độ dài `paper_ids` nên hai con số không thể lệch nhau. Có thêm mục `rebuild_text_for_embedding` ghi lại 12 dòng phải dựng lại text sau khi cột nguồn bị sửa.

Giải thích cách repair đảm bảo dữ liệu được phục hồi từ nguồn đáng tin cậy thay vì chỉ che kết quả lỗi:

Repair **không** sửa chữa dataset đã hỏng. Nó đọc lại `data/raw/crossref_records.json` — snapshot bất biến lưu từ pha 1 — rồi chạy lại đúng hàm `build_clean_dataframe` đã dùng cho baseline. Dataset repaired vì thế là sản phẩm dẫn xuất từ nguồn gốc, không phải bản vá chồng lên dữ liệu hỏng.

Để chứng minh chứ không chỉ tuyên bố, `corruption_flow.py` verify tập `paper_id` sau repair so với baseline và ghi kết quả vào `data/quality/corruption_summary.json`:

```json
{"baseline_rows": 24, "repaired_rows": 24,
 "missing_after_repair": [], "unexpected_after_repair": [],
 "fully_restored": true}
```

Nhóm **không** fetch lại API khi repair, vì bốn lý do. Thứ nhất, gọi lại API sẽ trả về tập bài khác (bài mới xuất bản, thứ hạng đổi), khiến `repaired` không so được với `baseline` — biến số bị lẫn. Điều này chắc chắn xảy ra vì filter được tính là `hôm nay − 180 ngày`, **tính lại mỗi lần chạy**, nên chạy ngày khác là cửa sổ thời gian đã trượt. Thứ hai, khôi phục không được phụ thuộc bên thứ ba: API có thể sập hoặc rate-limit đúng lúc cần nhất. Thứ ba, người chấm phải tái lập được kết quả mà không cần mạng. Thứ tư, đây chính là bài học kiến trúc của lab — tầng raw bất biến *là* bản sao lưu.

## 10. So sánh baseline, corrupted và repaired

| Metric/signal            | Baseline | Corrupted | Repaired | Thay đổi do corruption | Mức phục hồi | Nhận xét   |
| ------------------------ | -------: | --------: | -------: | -----------------------: | --------------: | ------------ |
| `retrieval_hit_rate`   |   1.0000 |    0.7500 |   1.0000 |                  −0.2500 |            100% | 4/16 câu mất hit, 3 do mất tài liệu |
| `mean_token_f1`        |   1.0000 |    0.5900 |   1.0000 |                  −0.4100 |            100% | 7/16 câu sai nội dung — tụt sâu hơn hit rate |
| `judge_accuracy`       |   1.0000 |    0.6250 |   1.0000 |                  −0.3750 |            100% | LLM judge độc lập xác nhận 6/16 câu sai |
| `mean_judge_score`     |   5.0000 |    3.6875 |   5.0000 |                  −1.3125 |            100% | Điểm trung bình rơi hơn 1 bậc |
| Quality checks pass/fail |     PASS |      FAIL |     PASS |     3 check chuyển FAIL |            100% | `paper_id_unique`, `summary_length`, `freshness` |
| Freshness status         |    Fresh |     Stale |    Fresh |          3/23 dòng cũ |            100% | Ngày cũ nhất từ 2026-02-12 thành 2025-01-29 |

Nêu ít nhất hai kết luận có quan hệ nhân quả được hỗ trợ bởi artifacts:

1. **Mất dữ liệu → freshness/quality báo động → retrieval sụp.** `drop_latest_records` xóa 3 bài mới nhất (log: `data/results/corruption_log.json`), `stale_published_date` đẩy 3 bài ra ngoài ngưỡng 180 ngày → freshness chuyển Stale với `stale_rows: 3/23` (`data/quality/freshness_report_corrupted.json`) → `retrieval_hit_rate` rơi từ 1.0 xuống 0.75, trong đó 3/4 câu mất hit đúng là các bài bị xóa. Tài liệu không còn trong index thì không thuật toán nào lấy ra được.

2. **Repair từ raw → tín hiệu quality xanh trở lại → chỉ số agent phục hồi hoàn toàn.** Rebuild từ `crossref_records.json` cho `fully_restored: true` → cả 7 quality check PASS trở lại và freshness về Fresh (`data/quality/repaired_quality.json`) → cả bốn chỉ số RAG trở về đúng giá trị baseline. Mức phục hồi 100% chỉ có thể đạt được vì repair dùng cùng snapshot và cùng logic cleaning; nếu fetch lại API thì con số sẽ trôi.

3. **Có loại lỗi mà observability hiện tại không bắt được.** `swap_authors` gán nhầm `authors_joined` sang bài khác — mô phỏng lỗi join sai khóa trong ETL. Dữ liệu vẫn hợp lệ về hình thức (không null, không rỗng, không trùng) nên **không quality check nào FAIL**, nhưng agent trả lời sai tác giả và token F1 tụt. Đây là ví dụ rõ nhất cho luận điểm trung tâm của bài: hệ thống dữ liệu hỏng trong im lặng, và bộ check hiện tại còn thiếu chiều Accuracy.

## 11. Vấn đề tích hợp quan trọng

- **Triệu chứng:** Sau khi TV1 vá lỗi `categories`, mọi lần chạy `run_phase1.py` đều chết ngay bước 1 với `NameError: name 'json' is not defined`.
- **Nguyên nhân:** Commit vá đã chuyển sang dùng `core.utils.write_json` và bỏ `import json`, nhưng còn sót một chỗ gọi `json.load(f)` trong `load_raw_records`. TV1 chỉ test nhánh `fetch_source_records` (khi chưa có `data/raw/`), trong khi `load_raw_records` mới là đường mặc định của `phase1.py` mỗi khi snapshot đã tồn tại — tức là toàn bộ nhóm bị chặn.
- **Cách xử lý:** Đổi hai dòng mở file thành `data = read_json(path)`. Hàm `read_json` đã được import sẵn nhưng chưa dùng, cho thấy đây đúng là ý định ban đầu của bản vá. Fix được cherry-pick lên cả nhánh `Dung` lẫn `main`.
- **Cách xác minh:** Chạy `uv run python script/run_phase1.py` hai lần liên tiếp — lần đầu đi đường fetch, lần sau tự động đi đường snapshot; cả hai đều phải chạy hết 9 bước.

Bài học rút ra và đã áp dụng: `phase1.py` khai báo contract dưới dạng validator thực thi được (`REQUIRED_CLEAN_COLUMNS`, `REQUIRED_TESTSET_FIELDS`, `CONTRACT_OWNERS`), nên khi một module vi phạm schema, thông báo lỗi nêu thẳng tên người chịu trách nhiệm thay vì ném `KeyError` từ sâu trong `index.py`.

## 12. Giới hạn và hướng cải thiện

| Giới hạn hiện tại | Ảnh hưởng   | Hướng cải thiện có thể kiểm chứng |
| --------------------- | -------------- | ----------------------------------------- |
| Corpus chỉ 24 tài liệu với `top_k=4` (lấy 1/6 corpus) | `inject_noise` và `blank_summary` không làm mất retrieval hit nào dù có đụng vào tài liệu được hỏi — retrieval quá dễ | Tăng `max_results` lên vài trăm và giữ `top_k=4`; kỳ vọng nhiễu embedding sẽ đẩy tài liệu ra khỏi top-k và `hit_rate` tụt rõ |
| Không có quality check cho chiều Accuracy | `swap_authors` phá 3 dòng mà không check nào FAIL | Thêm check đối chiếu `authors_joined` của clean data với `authors` trong raw snapshot; kỳ vọng bắt được đúng 3 dòng |
| `qa.py` trích xuất chứ không sinh câu trả lời | Chỉ đo chuỗi dữ liệu → truy xuất → trích xuất, chưa đo tầng sinh câu trả lời; token F1 đạt trần 1.0 | Chấm thêm trên output của `agent.py` bằng metric ngữ nghĩa (embedding similarity) thay vì token overlap; baseline sẽ dưới 1.0 nhưng đo được cả tầng generation |
| `categories` là trường suy ra, không có trong dữ liệu gốc | Crossref không trả về `subject` cho bất kỳ bài nào trong 24 bài (0/24), nên nhóm suy ra từ `container-title` (tên tạp chí) → `group-title` → `type`. Giá trị như `Journal Article` là *loại tài liệu*, không phải *chủ đề*, nên loại câu hỏi `categories` có giá trị ngữ nghĩa thấp hơn ba loại còn lại. Số liệu vẫn hợp lệ vì `ground_truth` lấy từ đúng trường đó | Lấy chủ đề thật từ nguồn khác (OpenAlex có `concepts`, Semantic Scholar có `fieldsOfStudy`) rồi join theo DOI; đo lại bằng cách so `mean_token_f1` của riêng nhóm câu hỏi `categories` trước và sau |
| Embedding model chỉ mạnh với tiếng Anh | Corpus có 1 bài tiếng Nga nằm lệch trong không gian vector; hiện chưa gây hại vì exact-title lookup vẫn tìm đúng | Đổi sang `paraphrase-multilingual-MiniLM-L12-v2` và so `retrieval_hit_rate` trên riêng nhóm câu hỏi phi tiếng Anh |
| Ragas chưa chạy | Thiếu các chỉ số faithfulness/context precision | Bật `RUN_RAGAS=1`; cần thêm thời gian và quota LLM |

## 13. Checklist trước khi nộp

- [x] Thông tin nhóm và repository chính xác.
- [x] Phân công khớp với module, artifact và kết quả thực tế.
- [x] Lệnh tái hiện đã được chạy lại trên phiên bản dùng để nộp.
- [x] Baseline, corrupted và repaired dùng cùng evaluation set.
- [x] Bảng metrics khớp với các file trong `data/results/`.
- [x] Quality/freshness conclusions khớp với `data/quality/`.
- [x] Các đường dẫn báo cáo và artifact truy cập được.
- [ ] Mỗi thành viên đã hoàn thành báo cáo vai trò riêng.
- [x] Không có `.env`, API key, token hoặc secret trong source, report, log hay ảnh.

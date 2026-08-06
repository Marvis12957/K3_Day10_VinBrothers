# Data Pipeline — Thiết Kế Chi Tiết (Day 10: Data Pipeline & Data Observability)

> Tài liệu mô tả cách data pipeline được thiết kế và vận hành trong repo này, đối chiếu trực tiếp với code trong `src/`.
> Pipeline xây dựng một hệ thống **RAG trên kho bài báo học thuật từ Crossref**, sau đó **chủ động bơm lỗi dữ liệu**, đo tác động lên agent, **repair** và so sánh 3 trạng thái.

---

## 1. Mục tiêu thiết kế

Pipeline được thiết kế để chứng minh bằng artifact và metrics rằng:

1. **Dữ liệu sạch → agent trả lời tốt** (baseline).
2. **Dữ liệu hỏng → agent trả lời tệ hơn** (corrupted), và observability phát hiện được tín hiệu hỏng trước khi người dùng nhận câu trả lời sai.
3. **Repair từ nguồn đáng tin (raw) → phục hồi chất lượng** (repaired) và so sánh được mức phục hồi.

Ba nguyên tắc sống còn (nhóm thống nhất theo lead):

- **Test set đóng băng 1 lần**: baseline / corrupted / repaired đều chấm trên đúng `data/eval/test_set.json`.
- **3 trạng thái dùng path + collection riêng**: không bao giờ ghi đè baseline.
- **Repair = chạy lại cleaning từ raw snapshot**, không sửa tay answers/metrics.

---

## 2. Kiến trúc tổng quan

```mermaid
flowchart TD
    subgraph PHA1[PHA 1 — Baseline (dữ liệu sạch)]
        A[Crossref REST API<br/>api.crossref.org/works] --> B[src/ingestion/crossref.py<br/>fetch + retry/backoff 429/503 + parse]
        B --> R1[data/raw/crossref_response.json<br/>raw gốc — nguồn repair pha 2]
        B --> R2[data/raw/crossref_records.json<br/>24 PaperRecord]
        R2 --> C[src/ingestion/cleaning.py<br/>normalize + age_days + text_for_embedding]
        C --> D[validate_clean_contract<br/>10 cột · paper_id unique · text không rỗng]
        D --> D1[data/clean/papers_clean.{csv,json}]
        D --> F[src/retrieval/index.py<br/>MiniLM-L6-v2 + ChromaDB cosine<br/>collection: papers-baseline]
        D --> E[src/evaluation/testset.py<br/>data/eval/test_set.json — FREEZE]
        E --> V[validate_testset_contract<br/>5 field · doc_ids không rỗng]
        F --> G[src/evaluation/metrics.py<br/>evaluate_pipeline]
        V --> G
        G --> M1[data/results/baseline_metrics.json]
        G --> M2[data/results/baseline_answers.json]
        D --> Q[src/observability/quality.py<br/>quality checks + freshness]
        M1 --> REP[src/observability/reporting.py<br/>data/reports/phase1_report.md]
        Q --> REP
    end

    subgraph PHA2[PHA 2 — Corruption / Repair / Comparison]
        D1 --> CO[src/ingestion/corruption.py<br/>8 loại lỗi có log]
        CO --> C1[data/clean/papers_clean_corrupted.{csv,json}]
        CO --> CL[data/results/corruption_log.json]
        C1 --> I2[index papers-corrupted]
        I2 --> E2[evaluate corrupted<br/>dùng test set đã freeze]
        E2 --> CM[data/results/corrupted_metrics.json]
        R1 --> RC[load_raw_records + build_clean_dataframe<br/>REPAIR từ raw]
        RC --> I3[index papers-repaired]
        I3 --> E3[evaluate repaired]
        E3 --> RM[data/results/repaired_metrics.json]
        CM --> CR[generate_corruption_report<br/>data/reports/corruption_report.md]
        RM --> CR
    end
```

---

## 3. Cấu hình & công nghệ

| Thành phần | Giá trị |
| --- | --- |
| Source | Crossref REST API — `https://api.crossref.org/works` |
| Query | `agentic retrieval augmented generation large language model` |
| Filter | `from-pub-date:{now-180d},has-abstract:true` |
| `max_results` | 24 |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` (normalized) |
| Vector store | ChromaDB persistent, metric **cosine** (`hnsw.space=cosine`) |
| `top_k` | 4 |
| Freshness threshold | 180 ngày (`settings.freshness_threshold_days`) |
| LLM provider | `LLM_PROVIDER` (gemini/openai/anthropic/openrouter/ollama/custom) |
| Random seed (testset + corruption) | `42` |
| Request | timeout 30s, retry tối đa 4 lần cho status `429`/`503` |

**Collections riêng cho 3 trạng thái** (tự suy ra từ đường dẫn embedding output):

| Trạng thái | Collection | Embedding manifest |
| --- | --- | --- |
| Baseline | `papers-baseline` | `data/embeddings/papers_embeddings.json` |
| Corrupted | `papers-corrupted` | `data/embeddings/papers_embeddings_corrupted.json` |
| Repaired | `papers-repaired` | `data/embeddings/papers_embeddings_repaired.json` |

> `index.py` lưu `persist_path` **tương đối** trong manifest để commit di chuyển được giữa các máy (portable).

---

## 4. Data contract (chốt ở checkpoint C1)

### 4.1 Clean schema — đúng 10 cột (owner: TV2)

```text
paper_id, title, summary, published, authors_joined, categories_joined,
age_days, text_for_embedding, abs_url, pdf_url
```

Ràng buộc được `phase1.validate_clean_contract` kiểm tra fail-fast (kèm tên owner):

- `paper_id`: **không null, không trùng**
- `text_for_embedding`: **không rỗng** (embedding mới có ý nghĩa)

### 4.2 Test set — đúng 5 field mỗi item (owner: TV2)

```text
id, question_type, question, ground_truth, ground_truth_doc_ids
```

Ràng buộc được `phase1.validate_testset_contract` kiểm tra:

- Thiếu field → lỗi ngay
- `ground_truth_doc_ids` **không rỗng** (nếu rỗng thì `retrieval_hit_rate` luôn = 0)

---

## 5. Chi tiết từng module

### 5.1 Ingestion — `src/ingestion/crossref.py` (TV1 — Hoàng Dũng)

**`PaperRecord`** (11 field): `paper_id, title, summary, authors, categories, primary_category, published, updated, abs_url, pdf_url, comment`.

**Fetch** (`fetch_source_records`):
- Build params từ `settings.source_query`, `source_filter`, `max_results`
- **Retry/backoff** cho `429` và `503` (Crossref hay rate-limit), timeout 30s, tối đa 4 lần
- Lưu **raw response gốc** → `data/raw/crossref_response.json` (đây là nguồn REPAIR pha 2)
- Parse → `PaperRecord` → lưu `data/raw/crossref_records.json`

**Parse** (`parse_crossref_payload`):
- `paper_id` = DOI; title lấy phần tử đầu, strip thẻ XML/JATS
- Summary từ `abstract`/`description`, bóc thẻ JATS `<jats:p>`, unescape HTML
- **Ngày fallback**:
  - `published`: `published → published-online → published-print → issued → created`
  - `updated`: `indexed → deposited → created`
- **Categories fallback**: `subject → container-title → group-title → type` (vì Crossref hiện ít trả `subject`; đảm bảo mọi record có ít nhất 1 category để sinh câu hỏi)
- Authors từ `author[]` (given+family / family / given / name); PDF từ `link[]` chứa `pdf`

**Load snapshot** (`load_raw_records`): đọc JSON → `PaperRecord` (dùng lại khi có snapshot, không gọi API).

### 5.2 Cleaning — `src/ingestion/cleaning.py` (TV2 — Trần Trung Hiếu)

`build_clean_dataframe(records, run_date) -> DataFrame(10 cột)`:

1. **Normalize** title/summary/authors/categories: strip tag XML/JATS, unescape, gộp whitespace.
2. **Parse ngày** `published` (fallback `updated`) — hỗ trợ `YYYY-MM-DD`, `YYYY-MM`, `YYYY`, ISO timestamp.
3. **`age_days`** = `(run_date.date() - published).days`.
4. **Cột ghép**: `authors_joined` (`, `-join, bỏ rỗng), `categories_joined`.
5. **`text_for_embedding`** = `"Title: {t}. Summary: {s}. Authors: {a}. Categories: {c}."` (bỏ phần rỗng) — không bao giờ rỗng.
6. **Lọc dữ liệu xấu**: bỏ record thiếu `paper_id`/`title`/`summary`, không parse được ngày; **dedupe** `paper_id` (giữ dòng đầu).
7. **Sort** `published` giảm dần (mới nhất trước) — giúp khái niệm "latest records" của corruption có nghĩa.

### 5.3 Test set — `src/evaluation/testset.py` (TV2 — Trần Trung Hiếu)

`build_test_set(df, output_path) -> list[dict(5 field)]`:

- `TEST_SET_SIZE = 16`, `random_state = 42` → **tái lập được, tạo 1 lần rồi đóng băng**.
- Chọn mẫu đại diện; bỏ title chứa nháy đơn `'` (sẽ không bao giờ exact-lookup được).
- **4 loại câu hỏi** phân bố đều, chỉ sinh loại paper trả lời được (thiếu authors/categories/date thì bỏ loại đó):
  - `summary` → `What is the main summary of the paper '{title}'?`
  - `authors` → `Who authored the paper '{title}'?`
  - `date` → `When was the paper '{title}' published?`
  - `categories` → `What categories does the paper '{title}' belong to?`
- **Cách đặt câu hỏi khớp luật cứng của `retrieval/qa.py`** (`_extract_answer`): authors kích hoạt `"who authored"`, date kích hoạt `"when was"`, categories kích hoạt `"what categories"`, summary rơi vào `first_sentence(summary)`.
- Tên bài báo để trong **nháy đơn** `'...'` → `qa.answer_question` dùng `re.search(r"'([^']+)'")` + `index.lookup` để exact-match đúng paper.
- `ground_truth` = chính xác output `_extract_answer` → token F1 = 1.0 khi retrieval đúng.
- `ground_truth_doc_ids = [paper_id]` của chính paper đó.

### 5.4 Embedding & vector store — `src/retrieval/` (code tham khảo)

- `embeddings.py`: `MiniLMEmbeddings` (sentence-transformers, normalize embeddings, lru_cache model).
- `index.py`: `LocalEmbeddingIndex`
  - `build()`: xoá collection cũ → tạo collection (cosine) → embed `text_for_embedding` → `collection.add` → ghi manifest JSON (chứa documents + metadata, path tương đối).
  - `search(query, top_k)`: embed query → `collection.query` → `SearchResult` (score = `1 - distance`).
  - `lookup(value)`: exact theo `paper_id` hoặc `title` (lowercase) — dùng cho QA.
  - `_build_documents`: metadata gồm `paper_id, title, published, authors_joined, categories_joined, summary, abs_url, pdf_url`.

### 5.5 QA & agent — `src/retrieval/qa.py`, `agent.py`

- `answer_question`: tìm title trong nháy đơn → `index.lookup` (exact) → luôn đưa paper đúng lên đầu; kết hợp `index.search` semantic; `_extract_answer` trả theo luật cứng (authors/date/categories/summary).
- `agent.py`: LangChain agent 2 tools (`semantic_search_papers`, `lookup_paper`), system prompt yêu cầu dùng tool trước khi trả lời; `build_llm` hỗ trợ 6 provider.

### 5.6 Evaluation — `src/evaluation/metrics.py`

`evaluate_pipeline(settings, index, test_set_path, metrics_path, answers_path)`:

- Với mỗi câu hỏi: `answer_question` → `_judge_answer` (LLM judge có fallback heuristic theo token F1) → tính `retrieval_hit` (có paper đúng trong `retrieved_doc_ids`).
- **Metrics chính**:
  - `retrieval_hit_rate` — tỉ lệ câu hỏi lấy đúng paper ground-truth
  - `mean_token_f1` — F1 token giữa ground_truth và answer
  - `judge_accuracy` — tỉ lệ judge đánh `correct`
  - `mean_judge_score` — điểm judge trung bình (1–5)
  - `ragas` — chạy thêm nếu `RUN_RAGAS=1` (answer_relevancy, context_precision, context_recall, faithfulness)
- Ghi `*_metrics.json` và `*_answers.json`.

### 5.7 Observability — `src/observability/quality.py` (TV3 — Quốc Tuấn)

**`run_data_quality_checks`** — 6 checks, ghi `data/quality/{name}_quality.json`, trả dict có key `passed`:

| Check | Điều kiện pass |
| --- | --- |
| `row_count` | > 0 |
| `required_columns_present` | đủ 10 cột contract |
| `paper_id_not_null` | không null |
| `paper_id_unique` | không trùng |
| `title_not_null` | không null/không rỗng |
| `summary_length` | ≥ 40 ký tự (avg length ghi trong detail) |
| `freshness` | `age_days <= 180` cho mọi dòng |

**`build_freshness_report`** — `latest_published`, `oldest_published`, `stale_rows`, `total_rows`, `is_fresh`; dùng chung hàm `_freshness_stats` với quality gate để hai báo cáo không bao giờ trái ngược nhau. Ngày không parse được tính là stale.

**`reporting.py`** (TV3) — sinh markdown:
- `generate_phase1_report` → `data/reports/phase1_report.md` (source summary, metrics, quality, freshness).
- `generate_corruption_report` → `data/reports/corruption_report.md` (bảng so sánh baseline/corrupted/repaired kèm delta, quality/freshness corrupted vs repaired, phần takeaways tự sinh).

### 5.8 Corruption — `src/ingestion/corruption.py` (TV4 — Văn Hiếu)

`corrupt_clean_dataframe(df, output_log_path) -> DataFrame` — 8 thao tác, **seed 42**, các nhóm dòng **không chồng lấn** để đọc được impact từng loại:

| # | Loại | Tỉ lệ | Mô tả & tác động |
| --- | --- | --- | --- |
| 1 | `drop_latest_records` | 12% | Xoá các record mới nhất → mất doc, ảnh hưởng freshness + retrieval |
| 2 | `blank_summary` | 12% | Xoá trắng summary → agent mất nội dung |
| 3 | `inject_noise` | 12% | Chèn chuỗi rác (`lorem ipsum ...`) vào summary → nhiễu embedding |
| 4 | `truncate_title` | 12% | Cắt title còn 12 ký tự → phá exact lookup theo title |
| 5 | `stale_published_date` | 16% | Đẩy published lùi 400 ngày **và tính lại `age_days`** → freshness fail |
| 6 | `swap_authors` | 14% | Xoay vòng `authors_joined` giữa các paper → lỗi join sai khóa "thầm lặng" |
| 7 | `rebuild_text_for_embedding` | — | **Bắt buộc** dựng lại text cho dòng đã đổi cột nguồn → embedding phản ánh đúng dữ liệu hỏng |
| 8 | `duplicate_rows` | 8% | Nhân bản dòng → phá ràng buộc `paper_id` unique |

**2 ràng buộc bắt buộc** (nếu bỏ qua thì corruption vô nghĩa):
- Sửa `published` → **phải tính lại `age_days`** (freshness check đọc `age_days`, không đọc `published`).
- Sửa cột trong `FIELDS_INSIDE_EMBEDDING_TEXT` → **phải dựng lại `text_for_embedding`** (ChromaDB nhúng cột này).

**Corruption log** `data/results/corruption_log.json`: `generated_at`, `random_seed`, `rows_before/after`, `distinct_paper_ids_affected`, từng operation với `type/description/rows_affected/paper_ids/details`.

### 5.9 Orchestration — `src/pipelines/` (TV5 — Thái Đức)

**`phase1.py` — Baseline (9 bước):**

1. `load_or_fetch_records`: dùng snapshot nếu có, chỉ fetch khi thiếu hoặc `REFRESH_SOURCE=1`
2. `build_clean_dataframe` → `validate_clean_contract` (fail-fast, ghi tên owner)
3. Lưu `papers_clean.{csv,json}`
4. Build index → `papers-baseline`
5. `load_or_build_test_set`: **tạo 1 lần rồi tái sử dụng** (`REFRESH_TEST_SET=1` để tạo lại) → `validate_testset_contract`
6. `evaluate_pipeline` → baseline metrics/answers
7. `run_data_quality_checks` → baseline_quality.json
8. `build_freshness_report` → freshness_report.json
9. `generate_phase1_report` → phase1_report.md + agent demo (bỏ qua nếu thiếu API key)

**`corruption_flow.py` — Pha 2 (7 bước):**

1. `require_baseline` — phải đủ artifact baseline, thiếu thì báo chạy phase1 trước
2. `corrupt_clean_dataframe` → `validate_corrupted_frame` (chỉ check đủ cột, không ép chất lượng — corrupted có chủ đích vi phạm contract) → `describe_corruption` (so sánh trực tiếp baseline vs corrupted: removed ids, blank summary, duplicate) → lưu corrupted artifacts
3. `evaluate_state("corrupted")` — index `papers-corrupted` + evaluate **trên test set đã freeze** + quality + freshness
4. **Repair**: `load_raw_records` → `build_clean_dataframe` lại từ raw → `validate_clean_contract` → `verify_repair` (kiểm tra `fully_restored`: đủ paper_id, đủ số dòng) → lưu repaired artifacts
5. `evaluate_state("repaired")` — index `papers-repaired` + evaluate + quality + freshness
6. `generate_corruption_report` → `data/reports/corruption_report.md`
7. Ghi `data/quality/corruption_summary.json` (corruption summary + repair verification + metrics 3 trạng thái) + in bảng so sánh console

---

## 6. Bản đồ artifact (`data/`)

| Thư mục | Artifact | Trạng thái |
| --- | --- | --- |
| `data/raw/` | `crossref_response.json`, `crossref_records.json` | Raw gốc + raw đã parse |
| `data/clean/` | `papers_clean*.{csv,json}` (baseline/corrupted/repaired) | Dữ liệu 10 cột |
| `data/embeddings/` | `papers_embeddings*.json` (3 trạng thái) | Manifest + documents |
| `data/chroma/` | ChromaDB persistent (3 collections) | Vector store |
| `data/eval/` | `test_set.json` | **Test set đóng băng** |
| `data/results/` | `*_metrics.json`, `*_answers.json`, `corruption_log.json`, `agent_demo_answers.json` | Kết quả đánh giá |
| `data/quality/` | `*_quality.json`, `freshness_report*.json`, `corruption_summary.json` | Observability |
| `data/reports/` | `phase1_report.md`, `corruption_report.md` | Báo cáo markdown |

---

## 7. Cách tái hiện

```bash
# Pha 1 — baseline
uv run python script/run_phase1.py
# hoặc: python script/run_phase1.py

# Pha 2 — corruption → evaluate → repair → compare
uv run python script/run_corruption_flow.py
```

Biến môi trường hữu ích:

```dotenv
REFRESH_SOURCE=1      # bỏ qua snapshot, fetch lại từ Crossref
REFRESH_TEST_SET=1    # sinh lại test set (mặc định KHÔNG — giữ đóng băng)
RUN_RAGAS=1           # bật pass Ragas (chậm hơn)
```

---

## 8. Các quyết định thiết kế quan trọng

| Quyết định | Lý do |
| --- | --- |
| Test set đóng băng từ baseline | Đảm bảo 3 trạng thái so sánh được trên cùng bộ câu hỏi; sinh lại giữa chừng sẽ làm mất giá trị bảng so sánh |
| Clean schema 10 cột cố định + fail-fast theo owner | Bắt lỗi contract từ sớm, mỗi người chịu trách nhiệm đúng module |
| Corruption có seed + log chi tiết | Tái lập được; `rows_affected` suy ra từ chính `paper_ids` nên không lệch số liệu |
| Rebuild `text_for_embedding` bằng cách thay chuỗi trên text gốc | Khác biệt embedding chỉ đến từ nội dung hỏng, không do đổi định dạng template |
| Freshness dùng chung 1 hàm `_freshness_stats` | Quality gate và freshness report không bao giờ trái kết quả |
| Repair = chạy lại cleaning từ raw, có `verify_repair` | Chứng minh phục hồi thật (đủ paper_id + đủ số dòng), không che lỗi bằng tay |
| Embedding manifest dùng path tương đối | Manifest portable, commit được giữa các máy |
| Categories fallback nhiều tầng | Đảm bảo mọi record có category → test set đủ 4 loại câu hỏi |

---

## 9. Cách đọc kết quả

- `data/results/baseline_metrics.json` — chất lượng baseline.
- `data/results/corrupted_metrics.json` vs `repaired_metrics.json` — so sánh delta để chứng minh:
  - `retrieval_hit_rate` giảm sau corruption (doc bị xoá/đổi nội dung → không retrieve đúng)
  - `mean_token_f1`, `judge_accuracy`, `mean_judge_score` giảm (nội dung sai)
  - Repair phục hồi về gần baseline
- `data/quality/*_quality.json` + `data/quality/freshness_report*.json` — bằng chứng observability phát hiện dữ liệu hỏng trước khi người dùng nhận câu trả lời sai.

---

## 10. Corruption & Repair — cách nhóm làm dữ liệu xấu đi và xử lý lại

### 10.1 Cách làm dữ liệu xấu đi (Corruption)

Thực hiện trong `src/ingestion/corruption.py` (TV4 — Văn Hiếu), chạy trong `corruption_flow.py` bước 2.
**8 thao tác có chủ đích**, seed cố định `42`, các nhóm dòng **không chồng lấn** để đọc được impact từng loại:

| # | Loại lỗi | Số dòng | Ví dụ thực tế (từ `corruption_log.json`) | Mục đích |
| --- | --- | --- | --- | --- |
| 1 | `drop_latest_records` | 3 | Xoá 3 paper mới nhất: `10.2118/234689-pa` (2026-08-01), `10.1007/s10278-026-02086-9`, `10.21203/rs.3.rs-10178277/v1` | Corpus 24 → 23 dòng, mất document khỏi index |
| 2 | `blank_summary` | 3 | Xoá trắng summary của `10.47576/2949-1894.2026.7.7.023`... | Agent mất nội dung trả lời |
| 3 | `inject_noise` | 3 | Chèn chuỗi rác `lorem ipsum qwerty zzz 12345 %%% asdf gibberish...` vào summary | Làm nhiễu embedding |
| 4 | `truncate_title` | 3 | `"Retrieval-Augmented Large Language Model Agents..."` → `"Retrieval-Au"` (12 ký tự) | Phá exact lookup theo title |
| 5 | `stale_published_date` | 3 | `2026-05-06` → `2025-04-01` (lùi 400 ngày) **+ tính lại `age_days`** | Freshness check phải fail |
| 6 | `swap_authors` | 3 | `"Nawari O. Nawari..."` ↔ `"AMOS MBEKI NYAGAR"` (xoay vòng) | Mô phỏng lỗi join sai khóa — "lỗi thầm lặng" |
| 7 | `rebuild_text_for_embedding` | 12 | Dựng lại text cho mọi dòng đã đổi cột nguồn | Đảm bảo embedding phản ánh dữ liệu hỏng |
| 8 | `duplicate_rows` | 2 | Nhân bản dòng `10.70121/001c.158711`, `10.21203/rs.3.rs-9882260/v1` | Phá ràng buộc `paper_id` unique |

**Kết quả thực tế:** 24 → 23 dòng, **20/24 paper_id bị ảnh hưởng**, toàn bộ ghi log vào `data/results/corruption_log.json` (kèm `paper_ids`, `rows_affected`, ví dụ before/after).

**2 ràng buộc "sống còn"** (nếu bỏ qua thì corruption không tạo tác động đo được):
- Sửa `published` → **phải tính lại `age_days`** (freshness check đọc `age_days`, không đọc `published`).
- Sửa cột trong `FIELDS_INSIDE_EMBEDDING_TEXT` → **phải dựng lại `text_for_embedding`** (ChromaDB nhúng cột này, không nhúng cột nguồn).

### 10.2 Tác động đo được lên agent

Cùng **một test set đã đóng băng** (16 câu, `data/eval/test_set.json`), chạy lại index + evaluate:

| Metric | Baseline | Corrupted | Delta |
| --- | ---: | ---: | ---: |
| `retrieval_hit_rate` | 1.000 | **0.750** | −0.25 |
| `mean_token_f1` | 1.000 | **0.590** | −0.41 |
| `judge_accuracy` | 1.000 | **0.625** | −0.375 |
| `mean_judge_score` | 5.000 | **3.688** | −1.31 |

⇒ Dữ liệu xấu làm agent **retrieve sai 4/16 câu** và trả lời kém rõ rệt (token F1 rơi 0.41). Quality/freshness cũng fail (paper_id trùng, summary rỗng, `age_days` vượt 180 ngày).

### 10.3 Cách xử lý lại dữ liệu (Repair)

**Nguyên tắc:** repair = **vứt bỏ dữ liệu hỏng, dựng lại từ nguồn đáng tin** — không vá tay file corrupted.

Quy trình trong `corruption_flow.py` bước 4:

```text
data/raw/crossref_records.json   ← raw snapshot do TV1 lưu từ đầu (nguồn REPAIR)
        │
        ▼
load_raw_records()               ← nạp lại 24 PaperRecord nguyên vẹn
        │
        ▼
build_clean_dataframe(records)   ← cleaning chạy LẠI từ raw
        │
        ▼
validate_clean_contract()        ← kiểm tra 10 cột, paper_id unique, text không rỗng
        │
        ▼
verify_repair()                  ← bằng chứng phục hồi THẬT
```

**`verify_repair`** so sánh trực tiếp repaired vs baseline (không chỉ "trông ổn"):

```json
{
  "baseline_rows": 24,
  "repaired_rows": 24,
  "missing_after_repair": [],      // không thiếu paper nào
  "unexpected_after_repair": [],   // không thừa paper nào
  "fully_restored": true           // khớp hoàn toàn
}
```

Sau đó nhóm **re-index sang collection `papers-repaired`** (riêng, không đè baseline), **evaluate lại trên test set cũ**, chạy quality + freshness, rồi sinh `data/reports/corruption_report.md` so sánh 3 trạng thái.

### 10.4 Kết quả phục hồi

| Metric | Baseline | Corrupted | Repaired | Phục hồi |
| --- | ---: | ---: | ---: | ---: |
| `retrieval_hit_rate` | 1.000 | 0.750 | **1.000** | ✅ 100% |
| `mean_token_f1` | 1.000 | 0.590 | **1.000** | ✅ 100% |
| `judge_accuracy` | 1.000 | 0.625 | **1.000** | ✅ 100% |
| `mean_judge_score` | 5.000 | 3.688 | **5.000** | ✅ 100% |

**Vì sao repair thành công tuyệt đối?** Vì raw snapshot (`crossref_response.json` + `crossref_records.json`) được lưu nguyên vẹn từ pha 1 — nguồn dữ liệu gốc không hề bị corrupt. Repair chỉ cần chạy lại cleaning từ nguồn này là dữ liệu trở về đúng baseline, chứng minh bằng `fully_restored = true`.

### 10.5 Chuỗi nhân quả (đúng yêu cầu rubric)

1. **Corruption** (drop latest + blank summary + noise + truncate title + stale date + swap authors + duplicate) → **quality/freshness signal fail** (paper_id trùng, summary rỗng, age_days > 180) → **agent metric tụt** (hit_rate 1.0→0.75, token F1 1.0→0.59).
2. **Repair** (rebuild từ raw + `verify_repair`) → **quality/freshness phục hồi** → **agent metric về baseline** (1.0/1.0/1.0/5).

Bằng chứng nằm ở: `data/results/corruption_log.json`, `data/quality/corruption_summary.json`, `data/reports/corruption_report.md` và 3 file `*_metrics.json`.

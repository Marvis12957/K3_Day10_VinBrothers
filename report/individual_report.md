# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Họ và tên       | Trần Trung Hiếu        |
| MSSV               | 2A202602002                |
| Khóa/Lớp         | K3                         |
| Tên nhóm         | Nhóm 5 — Day 10 Data Pipeline |
| Vai trò chính    | Data Model & Eval Set Owner |
| Repository         | https://github.com/Marvis12957/K3_Day10_2A202602030_TranHieu |
| Ngày hoàn thành | 2026-08-06                 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| ------------------ | --------------------- | ---------------- | ----------------- | ------------ |
| Cleaning & data model | `src/ingestion/cleaning.py` — `build_clean_dataframe`, `CLEAN_COLUMNS` | `list[PaperRecord]` từ TV1 (`data/raw/crossref_records.json`) | `data/clean/papers_clean.{csv,json}` (10 cột contract) | Hoàn thành |
| Evaluation set | `src/evaluation/testset.py` — `build_test_set`, `QUESTION_TYPES` | `pd.DataFrame` 10 cột từ cleaning | `data/eval/test_set.json` (16 câu, 4 loại, đóng băng) | Hoàn thành |

Chỉ nhận ownership cho phần mình trực tiếp thực hiện. Phần cleaning nằm giữa TV1 (raw → clean) và TV5 (index/eval); phần test set được `phase1.py` đóng băng và dùng chung cho cả 3 trạng thái.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| ------------------------------------ | ------------------------------------ | ---------------------------- |
| Kiểm thử cleaning/testset trên data thật, phát hiện `categories` rỗng 24/24 | TV1 — `src/ingestion/crossref.py` | Sau khi TV1 vá fallback `subject → container-title → group-title → type`, test set từ 3 loại câu hỏi lên đủ 4 loại |
| Xác minh contract chain clean → index → retrieval | TV5 — `src/pipelines/phase1.py` | Chứng minh clean df đủ metadata cho `LocalEmbeddingIndex._build_documents`, test set 16/16 doc id resolve |
| Viết tài liệu thiết kế + script demo | Cả nhóm / lead | `docs/DATA_PIPELINE_DESIGN.md`, `docs/EXPLAIN_PIPELINE.md`, `script/explain_pipeline.py` |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --------------------------- | ----------------------------- | ------------------------- | ----------------------- |
| Implement cleaning đúng 10 cột contract | `src/ingestion/cleaning.py` | `data/clean/papers_clean.{csv,json}` 24 rows | `validate_clean_contract` PASS (10 cột, `paper_id` unique, `text_for_embedding` không rỗng) |
| Implement test set đúng 5 field | `src/evaluation/testset.py` | `data/eval/test_set.json` 16 câu, 4 loại đều | `validate_testset_contract` PASS; 100% câu có `ground_truth_doc_ids` |
| Căn chỉnh câu hỏi khớp luật cứng `qa.py` | `_question`, `_ground_truth` trong testset.py | ground_truth khớp chính xác output `_extract_answer` | Mock simulation `qa._extract_answer` trả đúng 16/16, baseline `mean_token_f1 = 1.0` |
| Chạy thử pipeline trước khi lead merge | `cleaning.py` + `testset.py` trên data thật của TV1 | Index build 24 docs, semantic search + exact lookup hoạt động | `LocalEmbeddingIndex` dựng từ clean df, test set doc resolution 16/16 |

Nêu một output cụ thể mà phần việc của bạn tạo ra hoặc giúp xác minh:

`data/eval/test_set.json` — 16 câu hỏi thuộc 4 loại `summary / authors / date / categories`, mỗi câu có đủ 5 field và `ground_truth_doc_ids` không rỗng. Điểm mấu chốt: câu hỏi được đặt đúng các cụm từ mà `retrieval/qa.py` dùng luật cứng để trích câu trả lời (`who authored`, `when was`, `what categories`) và tên bài báo nằm trong dấu nháy đơn để `index.lookup` exact-match — nên khi retrieval đúng thì `ground_truth` khớp tuyệt đối với câu trả lời (token F1 = 1.0). Bộ đề này được đóng băng và dùng chung cho baseline/corrupted/repaired.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Phần của tôi nằm ở giữa pipeline: biến raw records (11 field của `PaperRecord`) thành **clean dataframe chuẩn 10 cột** để index và observability tiêu thụ, đồng thời tạo **evaluation set** mà chỉ số chất lượng đo được có ý nghĩa — tức câu trả lời của agent phải so được với `ground_truth` một cách trung thực.

### Cách triển khai

**Cleaning** (`build_clean_dataframe`): normalize title/summary/authors/categories (bóc tag XML/JATS dư, gộp whitespace); parse ngày với fallback `published → updated` (hỗ trợ `YYYY-MM-DD`, `YYYY-MM`, `YYYY`, ISO timestamp); tính `age_days` từ ngày published so với `run_date`; ghép `text_for_embedding` theo khuôn `Title: ... Summary: ... Authors: ... Categories: ...` (bỏ phần rỗng, không bao giờ rỗng); lọc dòng thiếu id/title/summary hoặc không parse được ngày; dedupe theo `paper_id` giữ dòng đầu; sắp xếp `published` giảm dần để khái niệm "latest records" của corruption có nghĩa.

**Test set** (`build_test_set`): chọn mẫu đại diện cố định (`random_state=42`) để tái lập được; với mỗi paper chỉ sinh loại câu hỏi mà paper trả lời được (thiếu authors/categories/date thì bỏ loại đó); tên bài báo để trong nháy đơn `'...'` vì `qa.py` dùng regex `r"'([^']+)'"` để exact-lookup; `ground_truth` lấy đúng giá trị mà `_extract_answer` sẽ trả về cho câu hỏi tương ứng (authors → `authors_joined`, date → `published`, categories → `categories_joined`, summary → `first_sentence(summary)`).

### Input, output và contract

| Thành phần | Mô tả |
| ------------------------------ | ------------------------------------------- |
| Input | `list[PaperRecord]` (TV1); `pd.DataFrame` 10 cột (cho testset) |
| Output | `data/clean/papers_clean.{csv,json}` (10 cột); `data/eval/test_set.json` (5 field) |
| Module phụ thuộc | `ingestion.crossref` (PaperRecord), `core.utils` (normalize/first_sentence/write_json), `retrieval/qa.py` (luật cứng) |
| Module sử dụng output | `pipelines/phase1.py` (validate + index + eval), `observability/quality.py`, `ingestion/corruption.py`, `pipelines/corruption_flow.py` |
| Điều kiện lỗi cần xử lý | summary trống → loại dòng; ngày không parse được → loại dòng; title chứa nháy đơn → không chọn vào test set; `categories` rỗng → bỏ qua loại câu hỏi categories thay vì bịa dữ liệu |

### Cách xác minh

```bash
uv run python script/run_phase1.py
```

- **Kết quả mong đợi:** clean dataframe đúng 10 cột, `paper_id` unique; test set 16 câu đủ 4 loại, `ground_truth_doc_ids` không rỗng.
- **Kết quả thực tế:** clean 24 rows đúng 10 cột; `test_set.json` 16 câu (summary 4, authors 4, date 4, categories 4); mock `qa._extract_answer` khớp ground_truth 16/16; index build 24 docs; 16/16 doc id resolve; baseline `1.0 / 1.0 / 1.0 / 5.0`.
- **Artifact/log:** `data/clean/papers_clean.{csv,json}`, `data/eval/test_set.json`, `data/results/baseline_metrics.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** `retrieval/qa.py` trả lời bằng **luật cứng chuỗi** (`_extract_answer`): chỉ nhận `who authored`/`list the authors`, `when was`/`publication date`/`published on`, `what categories`, và tìm title trong dấu nháy đơn. Nếu câu hỏi đặt không đúng cụm, agent trả lời sai mà trông giống hệt lỗi retrieval.
- **Các phương án đã cân nhắc:** (1) Đặt câu hỏi tiếng Việt/tự nhiên, không quan tâm `qa.py`. (2) Đặt câu hỏi tiếng Anh **khớp chính xác luật cứng**, title trong nháy đơn. (3) Sửa `qa.py` cho "thông minh hơn".
- **Phương án đã chọn:** (2).
- **Lý do:** `qa.py` là code tham chiếu dùng chung và thuộc phạm vi người khác — luật nhóm là "chỉ sửa file của mình". Chọn (2) giữ cho `ground_truth` và câu trả lời của agent nói "cùng một ngôn ngữ", token F1 có nghĩa, và không tạo chi phí/reproducibility rủi ro như sửa module chung.
- **Bằng chứng quyết định phù hợp:** Mock simulation `qa._extract_answer` trả đúng ground_truth 16/16; baseline `mean_token_f1 = 1.0` và `retrieval_hit_rate = 1.0` trên dữ liệu sạch.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Khi chạy test set trên data thật bản đầu của TV1, phân bố câu hỏi chỉ có 3 loại: `{'summary': 8, 'authors': 4, 'date': 4}` — thiếu hẳn loại `categories` dù `build_test_set` có sinh nó.
- **Lệnh hoặc bước tái hiện:** Chạy `build_test_set(build_clean_dataframe(records, run_date), path)` với `data/raw/crossref_records.json` bản đầu.
- **Nguyên nhân gốc:** `_feasible_types` chỉ sinh câu hỏi `categories` khi `categories_joined` không rỗng; nhưng toàn bộ 24 record của bản data đó có `categories = []` vì Crossref không trả `subject` cho hầu hết record và TV1 chưa có fallback. Không phải lỗi sinh câu hỏi, mà là **dữ liệu nguồn thiếu chiều dữ liệu**.
- **Cách xử lý:** Không tự sửa file của TV1 (đúng luật nhóm) — báo lead và TV1 kèm bằng chứng; TV1 thêm chuỗi fallback `subject → container-title → group-title → type`. Song song, tôi giữ thiết kế testset "graceful": tự bỏ loại câu hỏi không khả thi thay vì crash hoặc bịa dữ liệu.
- **Cách xác minh sau khi sửa:** Re-test với data mới — 24/24 record có categories, test set đủ 4 loại `{'summary': 4, 'authors': 4, 'date': 4, 'categories': 4}`, QA simulation vẫn 100%.
- **Điều học được:** Contract của một module chỉ lộ ra đầy đủ khi chạy trên **data thật**, không phải data mẫu tự dựng. Test set builder phải được thiết kế để xử lý thiếu dữ liệu một cách có chủ đích, và lỗi dữ liệu nên được báo lên owner chịu trách nhiệm thay vì tự vá chéo.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

**1. Dữ liệu đi từ Crossref đến vector index như thế nào?** `crossref.py` gọi `/works` với query và filter `from-pub-date` + `has-abstract`, lưu raw payload rồi parse thành `PaperRecord`. `cleaning.py` chuẩn hóa text, bóc thẻ JATS, parse ngày, tính `age_days`, ghép `text_for_embedding` từ title + summary + authors + categories, dedup theo `paper_id` và sắp xếp mới nhất trước. `index.py` đưa cột `text_for_embedding` qua MiniLM-L6-v2 thành vector rồi nạp vào ChromaDB kèm metadata (`paper_id`, `title`, `published`, `authors_joined`, `categories_joined`, `summary`, `abs_url`, `pdf_url`).

**2. Evaluation set và ground-truth document IDs dùng để đo ra sao?** Mỗi câu hỏi mang theo `ground_truth` (đáp án trích từ clean data) và `ground_truth_doc_ids` (`paper_id` chứa đáp án). `retrieval_hit_rate` đo giao giữa `retrieved_doc_ids` và `ground_truth_doc_ids` — đo tầng truy xuất; `mean_token_f1` so từ giữa câu trả lời và `ground_truth` — đo tầng nội dung. Tách hai tầng cho phép chẩn đoán: hit rate tụt thì hỏng embedding/index, hit rate giữ nguyên mà F1 tụt thì tài liệu lấy đúng nhưng nội dung bên trong đã sai.

**3. Quality checks khác freshness monitoring ở điểm nào?** Quality checks trả lời "dữ liệu có đúng dạng không" — đủ dòng, `paper_id` không null/không trùng, title không rỗng, summary đủ dài; chúng bắt lỗi cấu trúc và chạy được trên một snapshot đứng yên. Freshness trả lời "dữ liệu có còn kịp thời không" — so `age_days` với ngưỡng 180 ngày; đây là chiều duy nhất phụ thuộc **thời điểm chạy**: cùng một dataset hôm nay Fresh, sáu tháng sau tự động Stale mà không ai sửa gì.

**4. Vì sao phải dùng cùng test set cho cả ba trạng thái?** Vì đây là thí nghiệm có đối chứng — muốn quy kết thay đổi cho một biến thì mọi biến khác phải giữ nguyên. Nếu sinh lại bộ đề trên dữ liệu đã hỏng thì `ground_truth` cũng hỏng theo, agent trả lời sai vẫn được chấm đúng, và corruption trông như vô hại. Đó là lý do `load_or_build_test_set` chỉ sinh một lần và đóng băng.

**5. Repair được xem là thành công dựa trên artifact và metric nào?** Ba tầng bằng chứng. Tầng metric: bốn chỉ số RAG trở về đúng baseline (1.0/1.0/1.0/5.0). Tầng tín hiệu: `repaired_quality.json` 7/7 PASS, `freshness_report_repaired.json` `is_fresh: true`. Tầng dữ liệu, mạnh nhất: `corruption_summary.json` cho `missing_after_repair: []`, `unexpected_after_repair: []`, `fully_restored: true` — tập `paper_id` sau repair khớp baseline chính xác, không phải trùng số ngẫu nhiên.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| ---------------------- | -------: | --------: | -------: | ------------------------- |
| `retrieval_hit_rate` | 1.0000 | 0.7500 | 1.0000 | 4/16 câu mất hit; 3 trong số đó do tài liệu bị xóa hẳn khỏi corpus |
| `mean_token_f1` | 1.0000 | 0.5900 | 1.0000 | Tụt sâu hơn hit rate (−0.41) vì gồm cả bài lấy về đúng nhưng nội dung đã hỏng (summary rỗng/nhiễu, title cắt, authors đổi) |
| `judge_accuracy` | 1.0000 | 0.6250 | 1.0000 | LLM judge độc lập xác nhận cùng xu hướng, không phải tạo tác của công thức token |
| `mean_judge_score` | 5.0000 | 3.6875 | 5.0000 | Rơi hơn một bậc điểm (5 → 3.69) |
| Quality checks | PASS | FAIL (3/7) | PASS | `paper_id_unique`, `summary_length`, `freshness` chuyển FAIL |
| Freshness status | Fresh | Stale | Fresh | 3/23 dòng quá hạn; ngày cũ nhất 2026-02-12 → 2025-01-29 |

### Kết luận từ số liệu

1. **Xóa 3 bài mới nhất + làm cũ 3 ngày xuất bản** → freshness chuyển Stale (`stale_rows: 3/23`), `paper_id_unique` FAIL do duplicate → `retrieval_hit_rate` rơi 1.0 → 0.75 với 3/4 câu mất hit đúng là các bài bị xóa.

2. **Repair = rebuild từ `crossref_records.json` bằng lại `build_clean_dataframe`** → `fully_restored: true`, 7/7 quality check PASS, freshness về Fresh → cả bốn chỉ số RAG phục hồi 100% về baseline.

Corruption nào ảnh hưởng rõ nhất và vì sao?

`drop_latest_records` — gây 3 trong tổng số 4 câu mất retrieval hit. Lý do triệt để: tài liệu không còn trong index thì không thuật toán nào lấy ra được; các kịch bản khác chỉ làm *giảm chất lượng* tín hiệu, còn kịch bản này *xóa* tín hiệu.

Kết quả nào khác với kỳ vọng ban đầu?

Tôi kỳ vọng `inject_noise` và `blank_summary` sẽ làm mất retrieval hit vì chúng phá trực tiếp `text_for_embedding`. Nhưng số liệu cho thấy **cả hai không làm mất hit nào** dù có đụng vào 2 tài liệu trong test set. Giả thuyết: corpus chỉ 24 tài liệu với `top_k = 4` (1/6 toàn bộ corpus), vector bị nhiễu đẩy lệch vẫn dễ lọt top-4. Tôi đối chiếu từng `paper_id` trong `corruption_log.json` với `retrieval_hit` trong `corrupted_answers.json` và xác nhận hai kịch bản này chỉ làm hỏng `token_f1` chứ không hỏng retrieval — đúng phân kỳ "hit giữ, F1 tụt" mà câu 7.2 dự đoán.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. **Về data pipeline:** Một module chỉ "xong" khi chạy được trên data thật và đúng contract đầu ra. Cleaning của tôi nhìn qua thì hoàn chỉnh, nhưng giá trị thật đến từ chỗ `validate_clean_contract`/`validate_testset_contract` của TV5 chứng minh nó khớp với 10 cột và 5 field — contract fail-fast kèm owner là cách hiệu quả nhất để nhóm 5 người làm song song không vỡ pipeline.

2. **Về data quality/observability:** Test set là "thước đo" của cả thí nghiệm. Nếu thước đo không khớp cách agent trả lời (luật cứng trong `qa.py`) thì mọi con số sau đó đều lệch. Chất lượng của evaluation set quyết định chất lượng của kết luận, không phải độ dài pipeline.

3. **Về ảnh hưởng của dữ liệu đến RAG agent:** Dữ liệu hỏng không gây exception — pipeline vẫn xanh, agent vẫn trả lời trôi chảy, chỉ là sai. Tác động chỉ hiện ra khi đo trên bộ đề cố định: `drop_latest_records` làm 4/16 câu mất hit, `blank_summary`/`inject_noise` làm F1 rơi dù vẫn lấy đúng bài.

### Nếu có thêm thời gian

Tôi sẽ thêm dạng câu hỏi tổng hợp (so sánh hai paper) để ép agent phải dùng nhiều hơn một document, đồng thời tăng `max_results` lên vài trăm và đo lại để kiểm chứng giả thuyết "corpus nhỏ + top_k lớn che giấu tác động của noise" — nếu giả thuyết đúng, `retrieval_hit_rate` của corrupted sẽ tụt rõ hơn khi corpus lớn hơn.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Trần Trung Hiếu
**Ngày xác nhận:** 2026-08-06

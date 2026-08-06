# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin       | Nội dung                                                             |
| ---------------- | --------------------------------------------------------------------- |
| Họ và tên       | Phạm Quốc Tuấn                                                      |
| MSSV              | 2A202601983                                                            |
| Khóa/Lớp        | K3                                                                     |
| Tên nhóm        | Nhóm 5 — Day 10 Data Pipeline                                        |
| Vai trò chính   | Data Observability Owner                                              |
| Repository        | https://github.com/Marvis12957/K3_Day10_2A202602030_TranHieu          |
| Ngày hoàn thành | 2026-08-06                                                             |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| ------------------- | -------------------- | ---------------- | ----------------- | ----------- |
| Data quality checks | `src/observability/quality.py` — `run_data_quality_checks`, `_freshness_stats` | `pd.DataFrame` 10 cột theo contract C1, do TV2 (Trần Trung Hiếu — `cleaning.py`) và TV4 (Trần Văn Hiếu — `corruption.py`) tạo ra | `data/quality/{baseline,corrupted,repaired}_quality.json` | Hoàn thành |
| Freshness monitoring | `src/observability/quality.py` — `build_freshness_report` | Cùng dataframe, cột `age_days`/`published` | `data/quality/freshness_report{,_corrupted,_repaired}.json` | Hoàn thành |
| Markdown reporting | `src/observability/reporting.py` — `generate_phase1_report`, `generate_corruption_report` | 4 dict (`source_summary`, `metrics`, `quality`, `freshness`) do TV5 (Trương Công Thái Đức — `phase1.py`/`corruption_flow.py`) truyền vào | `data/reports/phase1_report.md`, `data/reports/corruption_report.md` | Hoàn thành |

Cả hai file tôi phụ trách xuất phát từ trạng thái stub (`raise NotImplementedError`, có pseudo-code sẵn); tôi cài đặt toàn bộ logic bên trong, không đổi chữ ký hàm vì `phase1.py` và `corruption_flow.py` đã gọi theo đúng interface đó.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| ---------- | ------------------------------- | --------- |
| Giữ đúng contract khóa `passed` (quality) và `is_fresh` (freshness) | TV5 (Trương Công Thái Đức) — `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py` | `main()` của cả hai pipeline đọc trực tiếp hai khóa này để in tóm tắt cuối chạy mà không cần sửa lại phía orchestration |

Ngoài mục trên, tôi không liệt kê thêm hoạt động hỗ trợ nào khác: lịch sử git của `quality.py`/`reporting.py` chỉ gồm một commit (`8752bda`), không có bằng chứng tôi trực tiếp debug module của thành viên khác như vai trò Integration của TV5 — nên tôi không nhận công cho phần việc không kiểm chứng được.

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| ----------------------- | ------------------------------ | ------------------- | --------------- |
| Cài 7 quality check (row count, required columns, paper_id null/unique, title null, summary length, freshness) | `run_data_quality_checks` | `data/quality/baseline_quality.json` (7/7 PASS), `corrupted_quality.json` (3/7 FAIL), `repaired_quality.json` (7/7 PASS) | `uv run python script/run_phase1.py` rồi `uv run python script/run_corruption_flow.py` |
| Gộp logic freshness dùng chung cho quality check và report riêng | `_freshness_stats` | `data/quality/freshness_report{,_corrupted,_repaired}.json` | Đối chiếu `stale_rows` giữa file freshness và dòng "freshness" trong file quality cùng trạng thái — luôn khớp |
| Sinh báo cáo markdown baseline (source + metrics + quality + freshness) | `generate_phase1_report` | `data/reports/phase1_report.md` | Mở file, đối chiếu số với `baseline_metrics.json`/`baseline_quality.json` |
| Sinh báo cáo markdown so sánh 3 trạng thái kèm takeaways tự động | `generate_corruption_report` | `data/reports/corruption_report.md` | Mở file, kiểm 4 dòng "Takeaways" tính đúng độ lệch so với `data/results/*_metrics.json` |

Output cụ thể do phần việc của tôi tạo ra:

Trong `generate_corruption_report`, tôi viết thêm hàm `_takeaways` — không có trong pseudo-code gốc (pseudo-code chỉ yêu cầu "viet markdown report so sanh"). Hàm này tự tính độ lệch từng metric giữa baseline/corrupted, suy ra mức phục hồi khi repaired, rồi in thành câu văn ngay trong `data/reports/corruption_report.md`, ví dụ:

> **Retrieval hit rate** dropped by 0.2500 after corruption (1.0000 -> 0.7500); repair recovered +0.2500 (-> 1.0000).

Tôi thêm phần này vì bảng số một mình không tự nói "cái gì đã hỏng và có phục hồi hay không" — người đọc phải tự trừ, còn với `_takeaways` thì báo cáo tự đọc được ngay cả với người không quen xem bảng.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Trước khi tôi viết, `quality.py` và `reporting.py` chỉ có chữ ký hàm và `raise NotImplementedError`. Phần của tôi phải trả lời hai câu hỏi tách biệt nhưng liên quan: (1) dữ liệu ở một trạng thái (baseline/corrupted/repaired) có "đúng dạng" không, và độc lập với đó, "có còn kịp thời không"; (2) làm sao để hai câu trả lời đó, cộng với metrics của TV5, biến thành một file markdown người đọc mở ra là hiểu ngay, không cần tự tra JSON.

### Cách triển khai

**Một nguồn sự thật cho "stale".** Cả `run_data_quality_checks` (check `"freshness"`) và `build_freshness_report` đều cần biết dòng nào cũ quá hạn. Thay vì viết công thức đó hai lần, tôi tách ra hàm riêng `_freshness_stats(df, settings)`, cả hai hàm public đều gọi lại nó. Freshness dùng `age_days` (đã tính sẵn ở bước cleaning) chứ không tính lại từ `published`, vì `age_days` mới là cột được cập nhật khi corruption đổi ngày xuất bản (`stale_published_date`) — dùng `published` trực tiếp ở đây sẽ bỏ lỡ hiệu ứng của corruption đó.

**Coi dữ liệu không đo được là "không đáng tin", không phải "bỏ qua".** `age_days` được ép kiểu số bằng `pd.to_numeric(..., errors="coerce")`, sau đó dòng nào cũ được xác định bằng `~(age_days <= threshold)` chứ không phải `age_days > threshold`. Khác biệt nằm ở cách hai phép so sánh xử lý `NaN`: nếu dùng `>`, một dòng có `age_days` là `NaN` sẽ cho kết quả `False` — tức "không cũ", lọt qua check một cách âm thầm. Dùng `~(<=)` thì `NaN <= threshold` là `False`, phủ định thành `True` — dòng đó bị tính là stale. Tôi chọn hướng "an toàn theo hướng nghiêm khắc hơn": không đo được tuổi thì không thể xác nhận là fresh.

**Check không đủ điều kiện thì báo lỗi thay vì crash.** Mỗi check đọc một cột cụ thể (`paper_id`, `title`, `summary`); nếu cột đó vắng mặt (ví dụ dataframe hỏng nặng hơn dự kiến), tôi không để `KeyError` ném ra giữa vòng lặp — mỗi nhánh có `else: add_check(..., False, "Column '...' missing.")`, nên hàm luôn trả về đủ 7 check thay vì crash giữa chừng và làm mất luôn 6 check còn lại.

**Reporting tách khỏi cấu trúc chi tiết của metrics.** `_metrics_section` chỉ in cứng 4 khóa đã biết trước (`retrieval_hit_rate`, `mean_token_f1`, `judge_accuracy`, `mean_judge_score`) theo đúng thứ tự, nhưng sau đó lặp qua toàn bộ `metrics.items()` và in thêm bất kỳ khóa nào không nằm trong `known_keys`. Nhờ vậy nếu TV5 thêm một metric mới vào `bundle.summary` (ví dụ điểm Ragas), báo cáo tự hiển thị mà không cần tôi sửa `reporting.py`.

### Input, output và contract

| Thành phần | Mô tả |
| ----------- | ------ |
| Input | `pd.DataFrame` 10 cột theo contract C1 (từ `cleaning.py`/`corruption.py`); dict `source_summary`, `metrics` (`bundle.summary`), `quality` (có khóa `passed`, `checks`), `freshness` (có khóa `is_fresh`) do `phase1.py`/`corruption_flow.py` truyền vào |
| Output | `data/quality/*.json` (7 file: quality + freshness cho 3 trạng thái), `data/reports/phase1_report.md`, `data/reports/corruption_report.md` |
| Module phụ thuộc | `core.config.Settings` (`freshness_threshold_days`, `paths.quality_dir`), `core.utils` (`now_utc`, `safe_slug`, `write_json`, `write_text`) |
| Module sử dụng output | `src/pipelines/phase1.py` (in `quality.get("passed")`, `freshness.get("is_fresh")` ở cuối chạy), `src/pipelines/corruption_flow.py` (dùng cùng hai hàm cho 2 trạng thái corrupted/repaired), `report/group_report.md` và các báo cáo cá nhân trích trực tiếp số liệu từ đây |
| Điều kiện lỗi cần xử lý | Thiếu cột bắt buộc (mỗi check tự báo `False` thay vì crash); `age_days` không parse được (`NaN` → tính là stale); dataframe rỗng (`_freshness_stats` trả `total_rows=0`, `is_fresh=False` thay vì chia cho 0) |

### Cách xác minh

```bash
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
```

- **Kết quả mong đợi:** baseline 7/7 quality check PASS và freshness Fresh; corrupted có ít nhất các check `paper_id_unique`, `summary_length`, `freshness` chuyển FAIL và freshness Stale; repaired quay lại 7/7 PASS và Fresh; hai file markdown phản ánh đúng các JSON trên.
- **Kết quả thực tế:** khớp đúng như trên — `baseline_quality.json` 7/7 PASS, freshness `stale_rows: 0/24`; `corrupted_quality.json` FAIL đúng 3 check (`paper_id_unique`: 2 trùng, `summary_length`: 3 dòng ngắn, `freshness`: 3/23 dòng quá hạn, cũ nhất `2025-01-29`); `repaired_quality.json` 7/7 PASS, freshness `0/24`, `latest_published`/`oldest_published` trở lại `2026-08-01`/`2026-02-12` như baseline. `data/reports/corruption_report.md` in đúng 4 dòng takeaways với số khớp `data/results/{corrupted,repaired}_metrics.json`.
- **Artifact/log:** `data/quality/*.json`, `data/reports/phase1_report.md`, `data/reports/corruption_report.md`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Pseudo-code có sẵn gợi ý viết freshness thành hai khối riêng — một khối "check freshness" bên trong `run_data_quality_checks`, một khối tổng hợp báo cáo riêng trong `build_freshness_report`. Cả hai đều cần cùng câu trả lời "dòng nào là stale".
- **Các phương án đã cân nhắc:** (1) Viết công thức stale riêng ở mỗi hàm, đúng như pseudo-code tách khối. (2) Rút thành hàm private dùng chung `_freshness_stats`, cả hai hàm public gọi lại. (3) Để `run_data_quality_checks` gọi `build_freshness_report` rồi đọc lại `is_fresh` từ kết quả đó.
- **Phương án đã chọn:** (2) — hàm `_freshness_stats` dùng chung.
- **Lý do:** Phương án (1) tạo rủi ro hai định nghĩa "stale" trôi dần theo thời gian nếu sau này chỉ một chỗ được sửa (ví dụ đổi `<=` thành `<`, hoặc quên cập nhật ngưỡng ở một trong hai nơi). Phương án (3) cũng dùng chung logic nhưng ép một thứ tự gọi bắt buộc giữa hai hàm public — trong khi `phase1.py` gọi `run_data_quality_checks` ở bước 7 và `build_freshness_report` ở bước 8 như hai bước độc lập, không có ràng buộc ai gọi trước ai. Phương án (2) giữ được cả hai hàm public độc lập mà vẫn không lặp logic.
- **Bằng chứng quyết định phù hợp:** Ở cả ba trạng thái đã chạy, số `stale_rows`/`total_rows` trong `freshness_report*.json` luôn khớp với chi tiết của check `"freshness"` trong `*_quality.json` cùng trạng thái (ví dụ corrupted: `3/23` ở cả hai file) — không có lần chạy nào hai con số lệch nhau.

## 6. Một lỗi hoặc blocker đã xử lý

Đây không phải một lỗi runtime (không có traceback) mà là một khoảng trống trong chính bộ check tôi viết ra, tôi phát hiện khi đối chiếu output của mình với `corruption_log.json` của TV4 — nên tôi ghi trung thực là **chưa xử lý xong** thay vì nhận là đã vá.

- **Triệu chứng:** `corrupted_quality.json` báo FAIL đúng 3 check (`paper_id_unique`, `summary_length`, `freshness`), nhưng kịch bản corruption `swap_authors` (hoán đổi `authors_joined` giữa 3 paper: `10.3390/buildings16132637`, `10.21203/rs.3.rs-9770645/v1`, `10.21079/11681/50309`) không làm bất kỳ check nào trong 7 check của tôi chuyển FAIL.
- **Lệnh hoặc bước tái hiện:**

```bash
uv run python script/run_corruption_flow.py
```

  rồi mở `data/results/corruption_log.json` (mục `"type": "swap_authors"`) đối chiếu với `data/quality/corrupted_quality.json` — không dòng `checks` nào nhắc tới 3 `paper_id` đó.
- **Nguyên nhân gốc:** 7 check tôi viết chỉ phủ 3 chiều chất lượng — Completeness (null/rỗng), Uniqueness (`paper_id` trùng), Validity (độ dài `summary`, `age_days` parse được). Không check nào đối chiếu **nội dung** `authors_joined` với nguồn gốc của nó. `swap_authors` chỉ hoán đổi các giá trị hợp lệ giữa các dòng hợp lệ — nhìn thuần theo hình thức thì dữ liệu vẫn không null, không rỗng, không trùng, nên "sạch" theo mọi tiêu chí tôi đã viết.
- **Cách xử lý:** Chưa vá trong phạm vi bài nộp này — đây là giới hạn đã xác nhận, không phải lỗi ẩn chưa bị phát hiện (xem "Nếu chưa xử lý xong" bên dưới).
- **Cách xác minh sau khi sửa:** Chưa áp dụng — chưa sửa.
- **Điều học được:** "Tất cả check đều PASS" chỉ chứng minh dữ liệu đúng những gì tôi *chọn* kiểm tra, không chứng minh dữ liệu đúng sự thật. Khi viết một quality check mới, giờ tôi tự hỏi thêm một bước: "kịch bản nào hoán đổi giá trị hợp lệ giữa các dòng hợp lệ sẽ lọt qua check này?" — vì đó là dạng lỗi nguy hiểm nhất: không có exception, không có test đỏ, hệ thống vẫn báo xanh.

Nếu chưa xử lý xong:

- **Phạm vi bị ảnh hưởng:** 3/24 dòng trong `corrupted_quality.json` có `authors_joined` sai mà không có tín hiệu FAIL nào đi kèm; ở tầng agent, câu hỏi loại `authors` bị trả lời sai nhưng quality signal vẫn im lặng.
- **Những gì đã loại trừ:** Không phải do `required_columns_present` (cột `authors_joined` vẫn tồn tại đủ) hay do `summary_length` (kịch bản này không đổi `summary`) — đã xác nhận bằng cách đọc trực tiếp từng dòng `checks` trong `corrupted_quality.json`, cả hai đều PASS đúng như dự đoán vì chúng thực sự không liên quan tới `authors_joined`.
- **Bước tiếp theo:** Thêm check `authors_accuracy` — đối chiếu `authors_joined` của dataframe đang kiểm với trường `authors` gốc trong `data/raw/crossref_records.json` theo từng `paper_id`. Kỳ vọng có thể kiểm chứng ngay: chạy lại `run_corruption_flow.py`, check mới phải FAIL đúng 3 dòng bị `swap_authors`, và tổng số FAIL trong `corrupted_quality.json` phải tăng từ 3 lên 4.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

**1. Dữ liệu đi từ Crossref đến vector index như thế nào?** `crossref.py` gọi `/works` với query cố định và filter theo ngày + có abstract, lưu nguyên payload thô vào `data/raw/crossref_response.json` rồi parse thành `data/raw/crossref_records.json`. `cleaning.py` chuẩn hóa text (bóc JATS, unescape HTML), parse ngày xuất bản, tính `age_days`, ghép 4 trường thành `text_for_embedding`, rồi dedup theo `paper_id`. `index.py` đưa `text_for_embedding` qua MiniLM-L6-v2 để lấy vector 384 chiều và nạp vào ChromaDB. Phần của tôi đứng ngay sau bước cleaning: mọi quality/freshness check tôi viết đều đọc trên đúng dataframe đã qua `cleaning.py`, trước khi nó bị biến thành vector — nên nếu dữ liệu sai từ bước này, check của tôi là tuyến phòng thủ đầu tiên phát hiện được, trước khi lỗi lan sang embedding.

**2. Evaluation set và ground-truth document IDs dùng để đo retrieval/answer quality ra sao?** Mỗi câu hỏi trong `test_set.json` mang `ground_truth` (câu trả lời đúng) và `ground_truth_doc_ids` (`paper_id` chứa đáp án đó). `retrieval_hit_rate` so `ground_truth_doc_ids` với tài liệu thực sự lấy về top-k; `mean_token_f1`/`judge_accuracy` so nội dung câu trả lời với `ground_truth`. Hai số liệu này đo tầng retrieval/answer — độc lập với 7 check của tôi, vốn đo tầng dữ liệu nguồn. Sự khác biệt này chính là lý do bảng so sánh 3 trạng thái có giá trị: quality/freshness đổi trước, rồi mới thấy metric agent đổi theo, hai tầng đo xác nhận lẫn nhau.

**3. Quality checks khác freshness monitoring ở điểm nào trong bài lab?** Đây là câu tôi trả lời chắc nhất vì là ranh giới tôi tự vẽ khi viết code. Quality checks trả lời "dữ liệu có đúng dạng không" tại một thời điểm đứng yên — đủ dòng, `paper_id` không null/không trùng, `title` không rỗng, `summary` đủ dài. Freshness trả lời một câu khác: "dữ liệu có còn kịp thời không", và nó là chiều **duy nhất phụ thuộc vào thời điểm chạy** — cùng một dataset hôm nay Fresh, quá ngưỡng 180 ngày thì tự động Stale dù không ai sửa gì. Tôi cố tình dùng chung `_freshness_stats` cho cả hai để chúng không bao giờ bất đồng, nhưng về mặt khái niệm chúng đo hai trục khác nhau: cấu trúc so với thời gian.

**4. Vì sao phải dùng cùng test set cho baseline, corrupted và repaired?** Vì đây là thí nghiệm có đối chứng — muốn quy kết chênh lệch chỉ số là do corruption thì mọi biến khác (câu hỏi, đáp án chuẩn, model chấm) phải giữ nguyên. Nếu sinh lại test set trên dữ liệu đã hỏng, `ground_truth` cũng hỏng theo và corruption sẽ trông vô hại một cách giả tạo. `phase1.py` chỉ sinh test set khi file chưa tồn tại; `corruption_flow.py` không có đường nào gọi lại `build_test_set`.

**5. Repair được xem là thành công dựa trên artifact và metric nào?** Từ góc nhìn observability của tôi, bằng chứng mạnh nhất không phải là 4 chỉ số RAG quay lại `1.0/1.0/1.0/5.0` (số trùng nhau có thể là trùng hợp), mà là `repaired_quality.json` cho 7/7 PASS và `freshness_report_repaired.json` cho `is_fresh: true`, `stale_rows: 0/24` — đúng bằng baseline, không chỉ "đủ tốt". Cộng thêm `corruption_summary.json` của TV5 xác nhận tập `paper_id` sau repair khớp tuyệt đối với baseline, ba lớp bằng chứng này (dữ liệu → quality/freshness → metric agent) cùng chỉ về một kết luận thay vì chỉ dựa vào một con số duy nhất.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| --------------- | --------: | ---------: | --------: | ----------------------- |
| `retrieval_hit_rate` | 1.0000 | 0.7500 | 1.0000 | Nằm ngoài phạm vi 7 check của tôi (đo ở tầng retrieval), nhưng tụt đúng lúc `freshness`/`paper_id_unique` chuyển FAIL — hai tín hiệu xảy ra cùng lần chạy |
| `mean_token_f1` | 1.0000 | 0.5900 | 1.0000 | Tụt sâu nhất trong 4 metric; một phần do `swap_authors` — kịch bản mà quality check của tôi không bắt được (xem mục 6) |
| `judge_accuracy` | 1.0000 | 0.6250 | 1.0000 | LLM judge xác nhận cùng xu hướng với token F1, không phải nhiễu riêng của công thức overlap |
| `mean_judge_score` | 5.0000 | 3.6875 | 5.0000 | Rơi hơn 1 bậc, phục hồi đúng về 5.0000 |
| Quality checks | 7/7 PASS | 3/7 FAIL (`paper_id_unique`, `summary_length`, `freshness`) | 7/7 PASS | Đúng bộ check tôi viết bắt được: trùng ID, summary rỗng, ngày quá hạn |
| Freshness status | Fresh (0/24 stale) | Stale (3/23 stale, cũ nhất 2025-01-29) | Fresh (0/24 stale) | `stale_published_date` đẩy 3 dòng vượt ngưỡng 180 ngày; `_freshness_stats` bắt đúng cả 3 |

### Kết luận từ số liệu

1. `stale_published_date` lùi ngày xuất bản 400 ngày trên 3 dòng và `age_days` được tính lại → check `freshness` của tôi chuyển FAIL (`freshness_report_corrupted.json`: `stale_rows: 3/23`), đồng thời `duplicate_rows` làm `paper_id_unique` FAIL (2 bản trùng) → 2 trong 4 chỉ số agent (`retrieval_hit_rate`, `judge_accuracy`) tụt trong cùng lần chạy corrupted.
2. Repair rebuild từ `data/raw/crossref_records.json` → cả 3 check từng FAIL (`paper_id_unique`, `summary_length`, `freshness`) quay lại PASS trong `repaired_quality.json`, freshness về `0/24` đúng như baseline → song song với đó cả 4 chỉ số RAG phục hồi 100% về giá trị baseline.

Corruption nào ảnh hưởng rõ nhất tới phần quality/freshness của tôi, và vì sao?

`stale_published_date` — vì nó là corruption duy nhất chạm trực tiếp vào công thức tôi viết (`age_days` so với ngưỡng), và tác động thể hiện rõ ràng nhất trên artifact của riêng tôi: `oldest_published` đổi từ `2026-02-12` (baseline) thành `2025-01-29` (corrupted), lệch hơn 1 năm dù chỉ đẩy lùi 400 ngày trên 3/24 dòng — vì corruption chọn đúng 3 dòng có ngày gần biên độ tuổi cũ nhất của corpus.

Kết quả nào khác với kỳ vọng ban đầu?

Tôi kỳ vọng bộ 7 check của mình đủ để "gác cổng" cho mọi corruption trong bài, vì đề bài liệt kê 7 kịch bản và tôi có 7 check. Nhưng đối chiếu từng kịch bản trong `corruption_log.json` với `corrupted_quality.json` cho thấy `swap_authors` và `inject_noise` không kích hoạt bất kỳ check nào — 2/7 kịch bản "lọt lưới" hoàn toàn về phía quality. Tôi xác minh bằng cách đọc thủ công từng `paper_id` trong hai operation đó và tìm trong `checks` xem có bị nhắc tới không — không có. Với `inject_noise` thì chấp nhận được vì bài không yêu cầu check "text rác trong summary"; nhưng với `swap_authors`, đây đúng là khoảng trống chiều Accuracy tôi ghi ở mục 6.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. **Về data pipeline:** Freshness không phải một thuộc tính tĩnh của dataset — nó phụ thuộc vào thời điểm bạn chạy check. Cùng một file `papers_clean.csv`, chạy hôm nay Fresh, để 6 tháng sau chạy lại có thể Stale mà không ai đụng vào dữ liệu. Viết `_freshness_stats` dùng chung dạy tôi phải tính lại freshness mỗi lần chạy, không được cache kết quả cũ.
2. **Về data quality/observability:** "PASS" là một phát biểu có phạm vi, không phải một bảo đảm tuyệt đối. Bộ check của tôi PASS 4/7 dòng trên dữ liệu bị `swap_authors` — không phải vì dữ liệu đúng, mà vì tôi chưa viết check nào đủ để phát hiện loại lỗi đó. PASS chỉ có nghĩa "không vi phạm những gì tôi đã nghĩ tới kiểm tra".
3. **Về ảnh hưởng của dữ liệu tới RAG agent:** Có sự khác biệt rõ giữa lỗi bị bộ check bắt (`paper_id_unique`, `freshness`) và lỗi lọt qua (`swap_authors`) — cả hai đều làm agent trả lời sai, nhưng chỉ loại đầu có tín hiệu cảnh báo đi kèm trong `data/quality/`. Với người vận hành hệ thống thật, loại lỗi thứ hai nguy hiểm hơn nhiều vì không có gì để nhìn vào trước khi agent đã trả lời sai cho người dùng thật.

### Nếu có thêm thời gian

Tôi sẽ thêm check `authors_accuracy` như đã nêu ở mục 6 — đối chiếu `authors_joined` với trường `authors` gốc trong `data/raw/crossref_records.json` theo `paper_id`. Cách đo cải thiện rõ ràng vì đã có ground truth sẵn trong `corruption_log.json`: chạy lại `run_corruption_flow.py`, check mới phải FAIL đúng 3 dòng bị `swap_authors` tác động, tổng số FAIL của `corrupted_quality.json` phải tăng từ 3 lên 4. Đây là khoảng trống duy nhất tôi xác định được mà toàn bộ observability hiện tại chưa phủ tới, nên ưu tiên vá trước các cải thiện khác.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Phạm Quốc Tuấn
**Ngày xác nhận:** 2026-08-06

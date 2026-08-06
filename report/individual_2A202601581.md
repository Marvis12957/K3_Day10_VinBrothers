# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Họ và tên       | Trương Công Thái Đức    |
| MSSV               | 2A202601581                |
| Khóa/Lớp         | K3                         |
| Tên nhóm         | Nhóm 5 — Day 10 Data Pipeline |
| Vai trò chính    | Integration & Comparison Owner (nhóm trưởng, review/merge code) |
| Repository         | https://github.com/Marvis12957/K3_Day10_VinBrothers |
| Ngày hoàn thành | 2026-08-06                 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao  | Trạng thái |
| ------------------ | --------------------- | ---------------- | ----------------- | ------------ |
| Baseline pipeline | `src/pipelines/phase1.py` — `main`, `validate_clean_contract`, `validate_testset_contract`, `load_or_build_test_set`, `json_safe_records`, `run_agent_demo` | Hàm của TV1–TV3 | `data/results/baseline_{metrics,answers}.json`, `data/reports/phase1_report.md`, `data/eval/test_set.json` | Hoàn thành |
| Corruption/repair flow | `src/pipelines/corruption_flow.py` — `main`, `require_baseline`, `validate_corrupted_frame`, `describe_corruption`, `verify_repair`, `evaluate_state` | Baseline artifacts + `corrupt_clean_dataframe` của TV4 | `data/results/{corrupted,repaired}_metrics.json`, `data/reports/corruption_report.md`, `data/quality/corruption_summary.json` | Hoàn thành |
| Data contract cho cả nhóm | `REQUIRED_CLEAN_COLUMNS`, `REQUIRED_TESTSET_FIELDS`, `CONTRACT_OWNERS` trong `phase1.py` | Thống nhất ở checkpoint C1 | Validator thực thi được, báo lỗi kèm tên owner | Hoàn thành |
| Review & merge | 5 nhánh của 5 thành viên | Code các thành viên | `main` tại `8e7d10c` | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| ------------------------------------ | ------------------------------------ | ---------------------------- |
| Phát hiện `categories` rỗng 24/24 và đề xuất chuỗi fallback | TV1 — `src/ingestion/crossref.py` | Sau khi vá: 24/24 record có categories, test set từ 3 loại câu hỏi lên đủ 4 loại |
| Tìm và sửa lỗi hồi quy `NameError: name 'json' is not defined` | TV1 — `load_raw_records` | Cherry-pick fix lên cả nhánh `Dung` và `main` (commit `57b3b5c`, `a54bcb7`) |
| Phát hiện đường dẫn tuyệt đối trong embedding manifest | `src/retrieval/index.py` (code tham chiếu) | Đổi sang đường dẫn tương đối; artifact commit lên không còn lộ path máy cá nhân |
| Cảnh báo trước hai cạm bẫy corruption (`age_days`, `text_for_embedding`) | TV4 — `src/ingestion/corruption.py` | TV4 xử lý đúng cả hai, corruption tạo được tác động đo được |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --------------------------- | ----------------------------- | ------------------------- | ----------------------- |
| Ghép 5 module rời thành baseline pipeline 9 bước | `src/pipelines/phase1.py` | 12 artifact trong `data/` | `uv run python script/run_phase1.py` chạy hết 9 bước |
| Đóng băng test set qua 3 trạng thái | `load_or_build_test_set` | `data/eval/test_set.json` sinh 1 lần, dùng lại 3 lần | Log in ra `Tai su dung test set da freeze` ở lần chạy thứ hai |
| Thí nghiệm corruption → repair → so sánh | `src/pipelines/corruption_flow.py` | `data/reports/corruption_report.md` bảng 3 cột | `uv run python script/run_corruption_flow.py` |
| Verify repair bằng số chứ không bằng cảm giác | `verify_repair` | `fully_restored: true` | `data/quality/corruption_summary.json` |
| Contract dạng validator có tên owner | `validate_clean_contract` | Lỗi schema báo thẳng người chịu trách nhiệm | Thử truyền dataframe thiếu cột → thông báo kèm `Owner: TV2 - Data Model Owner` |

Nêu một output cụ thể mà phần việc của tôi tạo ra hoặc giúp xác minh:

`data/quality/corruption_summary.json` là artifact của riêng tôi, không nằm trong yêu cầu đề bài. Nó ghi ba khối: `corruption` (số dòng trước/sau, danh sách `paper_id` bị xóa, số summary rỗng, số dòng trùng), `repair_verification` (`missing_after_repair`, `unexpected_after_repair`, `fully_restored`), và `metrics` gom cả ba trạng thái vào một chỗ. Tôi thêm nó vì bảng so sánh chỉ cho thấy con số *có* phục hồi, còn file này chứng minh dataset repaired *thực sự* khớp baseline chứ không phải trùng số một cách ngẫu nhiên.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Năm người viết 8 module song song trong 3.5 giờ, mỗi người chỉ thấy phần của mình. Vai của tôi là làm cho các mảnh đó ghép lại chạy được, và quan trọng hơn là **thiết kế thí nghiệm sao cho kết luận có giá trị** — vì một pipeline chạy trót lọt nhưng thiết kế sai thì vẫn cho ra bảng số liệu vô nghĩa.

### Cách triển khai

Tôi viết `phase1.py` **trước** các module khác, ngược thứ tự Guide. Lý do: file orchestration là nơi duy nhất nhìn thấy toàn bộ interface, nên nếu viết nó trước thì nó trở thành bản đặc tả sống cho 4 người còn lại, thay vì bản ghép nối thụ động ở cuối. Nhờ vậy tôi có thứ gửi nhóm ngay trong 20 phút đầu thay vì ngồi chờ.

Ba quyết định chính:

**Contract dạng validator có chủ sở hữu.** Thay vì để `index.py` ném `KeyError: 'authors_joined'` từ sâu bên trong, `validate_clean_contract` kiểm tra ngay sau bước cleaning và báo `Cleaned dataframe thieu cot ['authors_joined'] ... Owner: TV2 - Data Model Owner`. Với nhóm làm song song, thời gian tiết kiệm được nằm ở chỗ không ai phải đọc traceback của người khác.

**Đóng băng test set bằng code chứ không bằng lời dặn.** `load_or_build_test_set` chỉ sinh mới khi file chưa tồn tại hoặc `REFRESH_TEST_SET=1`; `corruption_flow.py` không có đường nào gọi `build_test_set`. Lời dặn miệng sẽ bị quên lúc 3 giờ chiều khi cả nhóm đang vội.

**Validator riêng cho dữ liệu corrupted.** Đây là chỗ tôi suýt sai. Ban đầu tôi định dùng lại `validate_clean_contract` cho cả corrupted frame, nhưng nhận ra dữ liệu corrupted **cố ý** vi phạm ràng buộc `paper_id` duy nhất và `text_for_embedding` không rỗng — đó chính là mục đích của nó. Nên tôi tách `validate_corrupted_frame` chỉ kiểm tra sự tồn tại của cột, đủ để `index.py` build được mà không ép ràng buộc chất lượng.

### Input, output và contract

| Thành phần | Mô tả |
| ------------------------------ | ------------------------------------------- |
| Input | `list[PaperRecord]` (TV1); `pd.DataFrame` 10 cột (TV2); `list[dict]` 5 field (TV2); `dict` có key `passed`/`is_fresh` (TV3); `corrupt_clean_dataframe(df, log_path)` (TV4) |
| Output | `data/results/*_metrics.json`, `data/results/*_answers.json`, `data/reports/{phase1_report,corruption_report}.md`, `data/quality/corruption_summary.json` |
| Module phụ thuộc | `ingestion.crossref`, `ingestion.cleaning`, `ingestion.corruption`, `evaluation.testset`, `evaluation.metrics`, `observability.quality`, `observability.reporting`, `retrieval.index` |
| Module sử dụng output | Không có module nào — output của tôi đi thẳng vào báo cáo và người chấm |
| Điều kiện lỗi cần xử lý | Thiếu artifact baseline khi chạy pha 2; dataframe corrupted vi phạm contract có chủ đích; agent demo lỗi do hết quota/không có key; `Timestamp` không serialize được sang JSON; content block nhiều phần của Gemini |

### Cách xác minh

```bash
rm data/eval/test_set.json
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
```

- **Kết quả mong đợi:** Baseline đạt gần trần trên dữ liệu sạch; corruption kéo cả bốn chỉ số xuống và làm quality/freshness chuyển FAIL; repair đưa mọi thứ về đúng baseline.
- **Kết quả thực tế:** Baseline 1.0/1.0/1.0/5.0, quality 7/7 PASS. Corrupted 0.75/0.59/0.625/3.6875, quality FAIL 3 check, freshness Stale. Repaired trở lại đúng 1.0/1.0/1.0/5.0, quality 7/7 PASS, `fully_restored: true`.
- **Artifact/log:** `data/results/*_metrics.json`, `data/quality/*.json`, `data/reports/corruption_report.md`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Ban đầu nhóm dùng Gemini làm LLM judge. Mỗi lần chạy corruption flow gọi 32 lượt, mất 5–8 phút vì `gemini-2.5-flash` bật thinking mặc định, và có lúc dính rate limit của free tier. Giữa buổi có phương án đổi sang OpenAI `gpt-4o-mini`.
- **Các phương án đã cân nhắc:** (1) Giữ Gemini, chấp nhận chậm. (2) Đổi sang OpenAI cho nhanh. (3) Bỏ LLM judge, dùng heuristic fallback có sẵn trong `metrics.py`.
- **Phương án đã chọn:** Đổi sang OpenAI `gpt-4o-mini`, **nhưng chạy lại cả ba trạng thái từ đầu**, không chỉ trạng thái còn dang dở.
- **Lý do:** Nếu chỉ đổi giữa chừng thì baseline do Gemini chấm còn repaired do OpenAI chấm — hai model khác thang điểm, `judge_accuracy` giữa ba trạng thái không còn so được với nhau. Mà model chấm chính là biến số thí nghiệm bắt buộc phải giữ cố định, y hệt lý do phải đóng băng test set. Tiết kiệm 1 phút mà mất tính hợp lệ của cả bảng so sánh là trao đổi tồi.
- **Bằng chứng quyết định phù hợp:** Sau khi chuyển, một lần chạy đầy đủ chỉ còn 52 giây (baseline) và 64 giây (corruption flow), so với 5–8 phút trước đó. Cả ba trạng thái trong `data/results/` đều do cùng `gpt-4o-mini` chấm, nên `judge_accuracy` 1.0 → 0.625 → 1.0 là so sánh hợp lệ.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:**

```
File "src/pipelines/phase1.py", line 106, in load_or_fetch_records
  return load_raw_records(raw_path), "snapshot"
File "src/ingestion/crossref.py", line 383, in load_raw_records
  data = json.load(f)
NameError: name 'json' is not defined
```

- **Lệnh hoặc bước tái hiện:** `uv run python script/run_phase1.py` khi `data/raw/crossref_records.json` đã tồn tại.
- **Nguyên nhân gốc:** Commit vá `categories` của TV1 chuyển sang dùng `core.utils.write_json` và bỏ `import json`, nhưng còn sót một chỗ gọi `json.load(f)` trong `load_raw_records`. TV1 chỉ test nhánh `fetch_source_records` (chạy khi chưa có `data/raw/`), trong khi `load_raw_records` mới là đường mặc định của `phase1.py` mỗi khi snapshot đã tồn tại — nghĩa là toàn bộ nhóm bị chặn chứ không riêng TV1.
- **Cách xử lý:** Đổi hai dòng mở file thành `data = read_json(path)`. Hàm `read_json` đã được import ở đầu file nhưng chưa dùng, xác nhận đây đúng là ý định của bản vá. Cherry-pick lên cả nhánh `Dung` (`a54bcb7`) lẫn `main` (`57b3b5c`) để nhánh của TV1 không còn lỗi nếu bạn ấy làm tiếp.
- **Cách xác minh sau khi sửa:** Chạy `run_phase1.py` hai lần liên tiếp — lần đầu đi đường fetch, lần sau tự động đi đường snapshot; cả hai đều chạy hết 9 bước và sinh đủ artifact.
- **Điều học được:** Một hàm có hai nhánh thực thi thì test một nhánh không nói lên gì về nhánh kia, nhất là khi nhánh chưa test lại là nhánh mặc định của mọi người khác. Ở vai review, tôi rút ra rằng đọc diff là không đủ — phải chạy thật trên đường đi mà người dùng thật sẽ đi. Lỗi này hoàn toàn không thể phát hiện bằng cách đọc code.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

**1. Dữ liệu đi từ Crossref đến vector index như thế nào?** `crossref.py` gọi `/works` với query và filter `from-pub-date` + `has-abstract`, lưu nguyên payload vào `crossref_response.json` rồi parse thành `PaperRecord` lưu ở `crossref_records.json`. `cleaning.py` chuẩn hóa text, bóc thẻ JATS, parse ngày, tính `age_days`, ghép `text_for_embedding` từ title + summary + authors + categories, dedup theo `paper_id` và sắp xếp mới nhất trước. `index.py` đưa cột `text_for_embedding` qua MiniLM-L6-v2 thành vector 384 chiều, nạp vào ChromaDB kèm metadata, với document ID dạng `{paper_id}::{index}` để bản sao trùng ID vẫn nạp được.

**2. Evaluation set và ground-truth document IDs dùng để đo ra sao?** Mỗi câu hỏi mang theo `ground_truth` (đáp án trích từ clean data) và `ground_truth_doc_ids` (`paper_id` chứa đáp án). Hai trường này đo hai tầng khác nhau: `retrieval_hit_rate` kiểm tra giao giữa `retrieved_doc_ids` và `ground_truth_doc_ids` — đo tầng truy xuất; `mean_token_f1` so từ giữa câu trả lời và `ground_truth` — đo tầng nội dung. Tách hai tầng cho phép chẩn đoán: hit rate tụt thì hỏng ở embedding/index, hit rate giữ nguyên mà F1 tụt thì tài liệu lấy đúng nhưng nội dung bên trong đã sai.

**3. Quality checks khác freshness monitoring ở điểm nào?** Quality checks trả lời "dữ liệu có đúng dạng không" — đủ dòng, `paper_id` không null và không trùng, title không rỗng, summary đủ dài. Chúng bắt lỗi cấu trúc và có thể chạy trên một snapshot đứng yên. Freshness trả lời "dữ liệu có còn kịp thời không" — so `age_days` với ngưỡng 180 ngày, và nó là chiều duy nhất phụ thuộc vào **thời điểm chạy**: cùng một dataset hôm nay Fresh, sáu tháng sau tự động Stale mà không ai sửa gì. Trong bài này TV3 tách `_freshness_stats` làm nguồn sự thật chung cho cả hai nên chúng không bao giờ bất đồng về định nghĩa "stale".

**4. Vì sao phải dùng cùng test set cho cả ba trạng thái?** Vì đây là thí nghiệm có đối chứng, muốn quy kết thay đổi cho một biến thì mọi biến khác phải giữ nguyên. Nếu sinh lại bộ đề trên dữ liệu đã hỏng thì `ground_truth` cũng hỏng theo, agent trả lời sai vẫn được chấm đúng, và corruption trông như vô hại. Cùng lý do đó, tôi không đổi model chấm giữa chừng.

**5. Repair được xem là thành công dựa trên artifact và metric nào?** Ba tầng bằng chứng, từ yếu đến mạnh. Tầng metric: bốn chỉ số RAG trở về đúng giá trị baseline. Tầng tín hiệu: `repaired_quality.json` cho 7/7 PASS và `freshness_report_repaired.json` cho `is_fresh: true`. Tầng dữ liệu, mạnh nhất: `corruption_summary.json` cho `missing_after_repair: []`, `unexpected_after_repair: []`, `fully_restored: true` — chứng minh tập `paper_id` sau repair khớp baseline chính xác, chứ không chỉ là các con số tình cờ bằng nhau.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| ---------------------- | -------: | --------: | -------: | ------------------------- |
| `retrieval_hit_rate` | 1.0000 | 0.7500 | 1.0000 | 4/16 câu mất hit, trong đó 3 do tài liệu bị xóa hẳn |
| `mean_token_f1` | 1.0000 | 0.5900 | 1.0000 | Tụt sâu hơn hit rate (−0.41 so với −0.25) vì gồm cả những bài lấy về đúng nhưng nội dung đã hỏng |
| `judge_accuracy` | 1.0000 | 0.6250 | 1.0000 | LLM judge độc lập xác nhận cùng xu hướng, không phải tạo tác của công thức token overlap |
| `mean_judge_score` | 5.0000 | 3.6875 | 5.0000 | Rơi hơn một bậc điểm |
| Quality checks | PASS | FAIL (3/7) | PASS | `paper_id_unique`, `summary_length`, `freshness` |
| Freshness status | Fresh | Stale | Fresh | 3/23 dòng quá hạn, ngày cũ nhất từ 2026-02-12 thành 2025-01-29 |

### Kết luận từ số liệu

1. **Xóa 3 bài mới nhất + làm cũ 3 ngày xuất bản** → freshness chuyển Stale (`stale_rows: 3/23`) và `paper_id_unique` FAIL → `retrieval_hit_rate` rơi 1.0 → 0.75, với 3 trong 4 câu mất hit đúng là các bài bị xóa.

2. **Rebuild từ `crossref_records.json` bằng lại `build_clean_dataframe`** → `fully_restored: true`, 7/7 quality check PASS trở lại, freshness về Fresh → cả bốn chỉ số RAG phục hồi 100% về đúng giá trị baseline.

Corruption nào ảnh hưởng rõ nhất và vì sao?

`drop_latest_records` — gây 3 trong tổng số 4 câu mất retrieval hit. Lý do triệt để: tài liệu không còn trong index thì không thuật toán nào lấy ra được, không có cách nào cứu vãn ở tầng dưới. Các kịch bản khác chỉ làm *giảm chất lượng* tín hiệu, còn kịch bản này *xóa* tín hiệu.

Kết quả nào khác với kỳ vọng ban đầu?

Tôi kỳ vọng `inject_noise` và `blank_summary` sẽ làm mất retrieval hit, vì chúng phá trực tiếp `text_for_embedding` — thứ được đưa vào vector. Nhưng số liệu cho thấy **cả hai không làm mất hit nào**, dù có đụng vào 2 tài liệu nằm trong test set.

Giả thuyết của tôi: corpus chỉ có 24 tài liệu mà `top_k = 4`, tức là mỗi truy vấn lấy về 1/6 toàn bộ corpus. Vector có bị nhiễu đẩy lệch đi thì tài liệu vẫn dễ dàng lọt top-4. Tôi kiểm tra bằng cách đối chiếu từng `paper_id` trong `corruption_log.json` với `retrieval_hit` của câu hỏi tương ứng trong `corrupted_answers.json`, và xác nhận cả hai kịch bản này chỉ làm hỏng `token_f1` (nội dung sai) chứ không hỏng retrieval. Cách kiểm chứng dứt điểm là tăng `max_results` lên vài trăm rồi đo lại — nếu giả thuyết đúng, hit rate sẽ tụt rõ.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. **Về data pipeline:** Tầng raw bất biến không phải là chi tiết lưu trữ mà là điều kiện để sửa sai. TV1 vá lỗi `categories` mà không tốn một lượt gọi API nào, chỉ vì payload gốc còn nguyên. Nếu chỉ lưu dữ liệu đã clean rồi ghi đè, cả nhóm đã phải fetch lại và corpus sẽ khác đi, kéo theo mọi số liệu trước đó thành vô giá trị.

2. **Về data quality/observability:** Bộ check chỉ bắt được những chiều mà nó được viết ra để bắt. Kịch bản `swap_authors` của TV4 phá 3 dòng, làm agent trả lời sai tác giả, mà **không một check nào FAIL** — vì dữ liệu vẫn không null, không rỗng, không trùng. Nó chỉ sai. Bài này dạy tôi rằng "tất cả check đều PASS" không đồng nghĩa với "dữ liệu đúng", và chiều Accuracy là chiều đắt nhất để giám sát vì phải đối chiếu với nguồn.

3. **Về ảnh hưởng của dữ liệu đến RAG agent:** Hỏng dữ liệu không làm hệ thống báo lỗi. Không có exception, không có test đỏ, pipeline vẫn chạy xanh và agent vẫn trả lời trôi chảy — chỉ là sai. Đó là lý do phải đo bằng số trên bộ đề cố định, vì không có cách nào khác để nhìn thấy nó.

### Nếu có thêm thời gian

Tôi sẽ thêm một quality check cho chiều Accuracy: đối chiếu `authors_joined` của clean dataset với trường `authors` trong `crossref_records.json`, dòng nào lệch thì FAIL. Cách đo cải thiện rất rõ ràng vì đã có sẵn ground truth: chạy lại corruption flow, check này phải bắt đúng 3 dòng mà `swap_authors` đã phá, và `corrupted_quality.json` phải chuyển từ 3 FAIL lên 4 FAIL. Đây là chỗ duy nhất trong bài mà lỗi lọt qua được toàn bộ chốt chặn observability, nên vá nó có giá trị cao nhất trên mỗi dòng code bỏ ra.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Trương Công Thái Đức
**Ngày xác nhận:** 2026-08-06

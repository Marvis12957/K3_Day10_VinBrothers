# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Hoàng Mạnh Dũng |
| MSSV | 2A202601213 |
| Khóa/Lớp | K3 |
| Tên nhóm | Nhóm 5 — Day 10 Data Pipeline |
| Vai trò chính | Source Ingestion Owner |
| Repository | https://github.com/Marvis12957/K3_Day10_2A202602030_TranHieu |
| Ngày hoàn thành | 2026-08-06 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Gọi nguồn Crossref | `src/ingestion/crossref.py` — `fetch_source_records` | `Settings`: query, filter, `max_results`, đường dẫn artifact | Payload Crossref và `list[PaperRecord]` | Hoàn thành |
| Parse và chuẩn hóa raw record | `parse_crossref_payload` cùng các hàm `_extract_*` | JSON response từ Crossref `/works` | 24 `PaperRecord` theo schema thống nhất | Hoàn thành |
| Lưu và nạp raw snapshot | `fetch_source_records`, `load_raw_records` | Payload API hoặc `data/raw/crossref_records.json` | `crossref_response.json`, `crossref_records.json` và danh sách record có kiểu | Hoàn thành |
| Tăng độ bền ingestion | Retry/backoff và xử lý dữ liệu thiếu/sai kiểu | HTTP 429/503, timeout, connection error, item không hợp lệ | Luồng fetch có thể retry; record lỗi không làm hỏng toàn bộ batch | Hoàn thành |

Phạm vi của tôi dừng ở tầng raw: bảo đảm dữ liệu đầu vào có nguồn gốc rõ ràng, parse ổn định và tái sử dụng được. Cleaning, test set, observability, corruption và orchestration do các owner khác phụ trách. Tuy nhiên, tôi vẫn đối chiếu output của mình với clean data, test set và repair artifact vì các bước đó phụ thuộc trực tiếp vào raw schema.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Bổ sung fallback cho `categories` khi Crossref không trả `subject` | TV2 — cleaning và test-set | 24/24 raw record có category; test set sinh đủ 4 câu hỏi loại `categories` |
| Giữ raw snapshot độc lập với clean data | TV4/TV5 — repair và integration | Repair dựng lại 24/24 record, không cần gọi lại API; `fully_restored: true` |
| Chuẩn hóa `published`, author, URL và abstract ngay ở raw schema | TV2 — `cleaning.py` | Tầng cleaning nhận schema nhất quán, đủ 24 record có author và publication date |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Cài đặt Crossref fetch và cơ chế retry | `fetch_source_records` | Gọi `/works` với query/filter/rows, timeout 30 giây; retry tối đa 4 lần cho 429, 503, timeout và connection error | Commit `1adaf65`, `f63aa0c`; đọc cấu hình và code |
| Parse payload thành data model | `PaperRecord`, `parse_crossref_payload` | 24/24 item được parse; 24 `paper_id` duy nhất | `data/raw/crossref_records.json` |
| Làm sạch text ở biên nguồn | `_clean_text` | Bóc XML/HTML, giải mã entity, chuẩn hóa khoảng trắng | Đối chiếu title/summary trong raw records |
| Xử lý trường metadata biến thiên | `_get_published`, `_get_updated`, `_extract_authors`, `_extract_categories`, `_extract_pdf_url` | 24/24 record có author, category và ngày xuất bản; 9/24 có PDF URL | Thống kê từ raw artifact |
| Lưu hai tầng raw artifact | `fetch_source_records` | Payload nguyên bản và snapshot đã parse được lưu riêng | `data/raw/crossref_response.json`, `data/raw/crossref_records.json` |
| Nạp lại snapshot để tái hiện | `load_raw_records` | Không phải gọi Crossref lại khi chạy pipeline/repair | Baseline và repaired đều có 24 record |

Hai commit thể hiện phần việc trực tiếp của tôi:

- `1adaf65`: triển khai `fetch_source_records`, `parse_crossref_payload`, `load_raw_records` và tạo raw artifacts.
- `f63aa0c`: bổ sung category fallback, retry cho `ConnectionError`, loại dữ liệu comment dạng cấu trúc gây nhiễu và thống nhất ghi JSON qua `write_json`.

Artifact đầu vào do phần ingestion tạo có 24 record, 24 `paper_id` duy nhất, 24 record có author, 24 record có category, 24 record có ngày xuất bản và 9 record có PDF URL. Payload API ghi nhận 24 item được lấy từ tập 100.916 kết quả phù hợp truy vấn.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Crossref trả metadata học thuật dưới dạng JSON nhưng các trường không hoàn toàn đồng nhất giữa các nhà xuất bản. Title có thể là list, abstract có thẻ JATS/XML, ngày có nhiều cấu trúc và nhiều trường fallback, author có thể thiếu given/family, `subject` thường rỗng, link PDF không phải record nào cũng có. Ngoài ra, API công khai có thể trả 429/503 hoặc lỗi mạng tạm thời.

Phần ingestion phải biến dữ liệu đó thành một contract ổn định cho cleaning mà vẫn giữ được payload gốc để kiểm tra và repair về sau.

### Cách triển khai

`fetch_source_records` tạo request từ `Settings`, gắn `User-Agent`, đặt timeout 30 giây và gọi Crossref. Với 429/503, hàm ưu tiên `Retry-After`; nếu không có thì dùng exponential backoff `2^attempt`. Timeout và `ConnectionError` cũng được retry. Sau khi nhận response hợp lệ, hàm lưu nguyên payload trước, rồi mới parse và lưu danh sách record.

`parse_crossref_payload` duyệt từng item độc lập. Record thiếu DOI hoặc title bị bỏ vì không đáp ứng khóa chính và điều kiện tối thiểu. Các lỗi cục bộ được ghi warning rồi bỏ record đó thay vì làm mất cả batch. Text được bóc tag, unescape HTML entity và chuẩn hóa whitespace.

Publication date dùng chuỗi fallback `published → published-online → published-print → issued → created`; update date dùng `indexed → deposited → created`. Author ưu tiên `given + family`, sau đó mới fallback sang một phần tên hoặc `name`.

Với category, Crossref hiện không trả `subject` cho phần lớn record. Tôi dùng fallback `subject → container-title → group-title → type`, loại chuỗi rỗng và khử trùng lặp không phân biệt hoa thường. Nhờ đó tầng test-set có dữ liệu để tạo câu hỏi category thay vì âm thầm thiếu một loại câu hỏi.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | `Settings` chứa `source_query`, `source_filter`, `max_results` và các đường dẫn; hoặc file JSON snapshot khi load lại |
| Output trong bộ nhớ | `list[PaperRecord]` với 11 trường: `paper_id`, `title`, `summary`, `authors`, `categories`, `primary_category`, `published`, `updated`, `abs_url`, `pdf_url`, `comment` |
| Output trên đĩa | `data/raw/crossref_response.json` và `data/raw/crossref_records.json` |
| Module phụ thuộc | `core.config.Settings`, `core.utils.read_json/write_json`, `requests` |
| Module dùng output | `src/ingestion/cleaning.py`, `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py` |
| Điều kiện lỗi cần xử lý | Rate limit, lỗi dịch vụ, timeout/mất kết nối, payload sai cấu trúc, item không phải dict, thiếu DOI/title, field sai kiểu |

### Cách xác minh

```bash
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
```

- **Kết quả mong đợi:** fetch/parse được raw records; baseline chạy từ raw input; repair dựng lại dữ liệu từ snapshot đã lưu.
- **Kết quả thực tế:** 24 raw records được lưu, baseline đạt 24 dòng; repaired dataset trở lại 24 dòng với tập ID khớp baseline.
- **Artifact/log:** `data/raw/crossref_response.json`, `data/raw/crossref_records.json`, `data/quality/corruption_summary.json`.

Trong lúc hoàn thiện báo cáo, tôi đối chiếu trực tiếp các artifact đã commit và lịch sử Git; không đưa API key hay nội dung `.env` vào báo cáo.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Pipeline cần dữ liệu để chạy baseline, nhưng cũng phải repair chính xác sau khi cố ý làm hỏng clean dataset.
- **Các phương án đã cân nhắc:** (1) mỗi lần chạy lại gọi Crossref; (2) chỉ lưu bản đã parse/clean; (3) lưu cả response nguyên bản và raw records đã parse.
- **Phương án đã chọn:** lưu hai tầng raw artifact: payload API nguyên bản để truy vết và `PaperRecord` snapshot để các bước sau dùng ổn định.
- **Lý do:** Gọi lại API có thể trả corpus khác do dữ liệu và thứ tự kết quả thay đổi theo thời gian. Chỉ lưu clean data thì không còn nguồn độc lập để sửa lỗi cleaning/corruption. Hai snapshot tăng dung lượng lưu trữ nhưng đem lại reproducibility, auditability và một nguồn repair không bị corruption chạm vào.
- **Bằng chứng quyết định phù hợp:** repair từ `crossref_records.json` trả lại 24/24 record; `missing_after_repair` và `unexpected_after_repair` đều rỗng; `fully_restored: true`; toàn bộ metrics repaired trở về đúng baseline.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** Sau lần fetch đầu, 24/24 record có `categories` rỗng khi parser chỉ đọc `subject`. Test set vì thế không thể tạo đủ nhóm câu hỏi category.
- **Bước tái hiện:** đọc `message.items[*].subject` trong `crossref_response.json`, sau đó kiểm tra trường `categories` trong raw records.
- **Nguyên nhân gốc:** Crossref không còn cung cấp `subject` ổn định cho phần lớn kết quả của truy vấn này; parser ban đầu phụ thuộc vào một field không đủ tin cậy.
- **Cách xử lý:** sửa `_extract_categories` để fallback lần lượt sang `container-title`, `group-title` và `type`, đồng thời chuẩn hóa và deduplicate category.
- **Cách xác minh sau khi sửa:** `data/raw/crossref_records.json` có category ở 24/24 record; `data/eval/test_set.json` có 4/16 câu hỏi thuộc `question_type=categories`.
- **Điều học được:** Với API bên ngoài, field “đúng schema” chưa chắc có độ phủ đủ cho nghiệp vụ. Contract nội bộ cần fallback có thứ tự và phải được xác minh bằng artifact downstream, không chỉ bằng việc request trả HTTP 200.

Trong bước tích hợp sau đó, việc chuyển sang `read_json/write_json` còn làm lộ một chỗ gọi `json.load` cũ trong `load_raw_records`. TV5 phát hiện và sửa ở commit `57b3b5c`/`a54bcb7`. Tôi ghi nhận đây là lỗi hồi quy ở ranh giới module: cả nhánh fetch mới và nhánh load snapshot mặc định đều cần được kiểm thử sau refactor.

## 7. Hiểu biết về luồng end-to-end

**1. Dữ liệu đi từ Crossref đến vector index như thế nào?** Crossref `/works` nhận query/filter và trả payload. Tầng ingestion lưu response nguyên bản, parse từng item thành `PaperRecord` rồi lưu snapshot raw. Cleaning đọc snapshot này, chuẩn hóa thành dataframe 10 cột, tính `age_days` và ghép `text_for_embedding`. MiniLM mã hóa text thành vector 384 chiều, sau đó ChromaDB lưu vector cùng metadata để truy vấn top-k.

**2. Evaluation set và ground-truth document IDs dùng để đo retrieval/answer quality ra sao?** Mỗi sample có câu hỏi, đáp án chuẩn, loại câu hỏi và `ground_truth_doc_ids`. Retrieval hit khi top-k chứa đúng `paper_id`; câu trả lời được so với ground truth bằng token F1 và LLM judge. Vì `paper_id` bắt nguồn từ DOI ở tầng ingestion nên tính ổn định và duy nhất của khóa này ảnh hưởng trực tiếp đến phép chấm.

**3. Quality checks khác freshness monitoring ở điểm nào?** Quality checks kiểm tra các ràng buộc như đủ cột, không null, khóa duy nhất, title/summary hợp lệ. Freshness đo tính kịp thời dựa trên `age_days` và ngưỡng 180 ngày. Một record có thể đúng schema nhưng vẫn quá cũ; ngược lại, record mới vẫn có thể thiếu trường hoặc trùng ID.

**4. Vì sao phải dùng cùng test set cho ba trạng thái?** Giữ cùng câu hỏi, ground truth và document IDs giúp corruption là biến thay đổi chính. Nếu sinh lại test set từ dữ liệu hỏng, các tài liệu bị xóa sẽ biến mất khỏi đề và điểm số có thể tốt giả tạo.

**5. Repair được xem là thành công dựa trên artifact và metric nào?** Trước hết phải khôi phục dữ liệu: 24 dòng, không thiếu/thừa `paper_id`, `fully_restored: true`. Tiếp theo, 7/7 quality check phải PASS và freshness trở lại Fresh. Cuối cùng, bốn metrics repaired phải trở về mức baseline. Trong kết quả hiện tại, cả ba tầng bằng chứng đều thỏa mãn.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét cá nhân |
| --- | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.0000 | 0.7500 | 1.0000 | Mất 4/16 retrieval hit; 3 bài bị xóa khỏi nguồn clean là tác động không thể bù ở tầng truy xuất |
| `mean_token_f1` | 1.0000 | 0.5900 | 1.0000 | Nội dung hỏng làm chất lượng câu trả lời giảm mạnh hơn mức giảm hit rate |
| `judge_accuracy` | 1.0000 | 0.6250 | 1.0000 | Corruption làm 6/16 câu không còn được judge chấp nhận |
| `mean_judge_score` | 5.0000 | 3.6875 | 5.0000 | Điểm trung bình giảm 1.3125 rồi phục hồi hoàn toàn |
| Quality checks | PASS (7/7) | FAIL (3/7) | PASS (7/7) | Trùng ID, summary ngắn và freshness bị phát hiện |
| Freshness status | Fresh | Stale | Fresh | Corrupted có 3/23 dòng quá 180 ngày; repaired còn 0/24 |

### Kết luận từ số liệu

1. Xóa 3 bài mới nhất, làm rỗng/cắt/nhiễu nội dung và tạo duplicate → quality chuyển từ PASS sang FAIL, freshness chuyển Fresh sang Stale → hit rate giảm 0,25; token F1 giảm 0,41; judge accuracy giảm 0,375.
2. Dựng lại clean data từ raw snapshot do ingestion lưu → tập `paper_id` khớp baseline, quality và freshness phục hồi → cả bốn metrics trở về đúng baseline.

Corruption ảnh hưởng rõ nhất là `drop_latest_records`. Khi một DOI không còn trong clean dataset và vector index, truy vấn không thể lấy đúng tài liệu dù embedding hoặc LLM tốt đến đâu. Ba trong bốn câu mất retrieval hit liên quan trực tiếp đến ba record bị xóa. Điều này cho thấy độ đầy đủ của ingestion/source snapshot là điều kiện cần trước khi tối ưu retrieval.

Kết quả khác kỳ vọng là nhiễu summary và title không làm hit rate giảm tương ứng với mức hỏng nội dung. Corpus chỉ có 24 tài liệu nhưng mỗi truy vấn lấy top 4, nên xác suất tài liệu vẫn nằm trong top-k khá cao. Tuy vậy token F1 và judge score vẫn giảm, chứng minh “retrieval có hit” không đồng nghĩa câu trả lời còn đúng.

Từ góc nhìn source owner, category fallback cũng có trade-off: `container-title` hoặc `type` giúp bảo đảm độ phủ 24/24 nhưng không giàu ngữ nghĩa bằng taxonomy subject thật. Đây là fallback phục vụ tính đầy đủ, không nên được diễn giải như phân loại học thuật chuẩn tuyệt đối.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. **Về data pipeline:** Raw response và parsed snapshot phải được lưu tách khỏi clean data. Đây là nền tảng để tái hiện, audit và repair mà không phụ thuộc trạng thái thay đổi của API ngoài.
2. **Về data quality/observability:** HTTP 200 hay parse thành công chưa đủ chứng minh ingestion tốt. Cần đo độ phủ từng field quan trọng và kiểm tra downstream contract; trường hợp category rỗng là ví dụ cụ thể.
3. **Về ảnh hưởng đến RAG:** Thiếu record ở tầng nguồn làm retrieval thất bại tuyệt đối, còn metadata sai có thể âm thầm làm câu trả lời sai dù hệ thống vẫn chạy. Chất lượng RAG bị giới hạn bởi chất lượng corpus trước khi phụ thuộc vào model.

### Nếu có thêm thời gian

Tôi sẽ bổ sung unit test dùng Crossref fixtures cho các trường hợp title dạng list, abstract có JATS, ngày chỉ có năm/tháng, thiếu author, `subject` rỗng, comment dạng dict, 429/503 và `ConnectionError`. Đồng thời, raw snapshot nên có manifest gồm query, filter, thời điểm fetch, số item, checksum và phiên bản schema. Cải thiện được đo bằng coverage các nhánh parser/retry và khả năng phát hiện snapshot bị thay đổi ngoài ý muốn trước khi pipeline chạy.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Hoàng Mạnh Dũng

**Ngày xác nhận:** 2026-08-06

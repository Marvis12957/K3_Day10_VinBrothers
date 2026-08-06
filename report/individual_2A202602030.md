# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| ------------------ | -------------------------- |
| Họ và tên | Trần Văn Hiếu |
| MSSV | 2A202602030 |
| Khóa/Lớp | K3 |
| Tên nhóm | Nhóm VinBrothers |
| Vai trò chính | TV4 — Corruption & Repair Owner |
| Repository | https://github.com/Marvis12957/K3_Day10_2A202602030_TranHieu |
| Ngày hoàn thành | 2026-08-06 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| ------------------ | --------------------- | ---------------- | ----------------- | ------------ |
| Bộ kịch bản corruption | `src/ingestion/corruption.py` — `corrupt_clean_dataframe` | Cleaned DataFrame 10 cột của TV2 | DataFrame đã corrupt → `data/clean/papers_clean_corrupted.{csv,json}` | Hoàn thành |
| Corruption log kiểm toán được | `_operation`, `_paper_ids` trong `corruption.py` | Index dòng bị đổi ở từng kịch bản | `data/results/corruption_log.json` — 8 operation, `rows_affected` + `paper_ids` từng dòng | Hoàn thành |
| Hai invariant bắt buộc sau khi corrupt | `_age_days`, `_rebuild_text_for_embedding`, hằng `FIELDS_INSIDE_EMBEDDING_TEXT` | Cột `published` và 4 cột nguồn của `text_for_embedding` | `age_days` và `text_for_embedding` luôn nhất quán với dữ liệu đã hỏng | Hoàn thành |
| Tính tái lập của thí nghiệm | `RANDOM_SEED = 42`, pool dòng không chồng lấn | — | Cùng input → cùng corrupted dataset và cùng log | Hoàn thành |

Tôi **không** sở hữu bước repair. Repair nằm trong `corruption_flow.py` của TV5 và đi thẳng từ `data/raw/crossref_records.json` qua `build_clean_dataframe` của TV2, cố tình không dùng lại bất cứ thứ gì trong file của tôi — đúng nguyên tắc "repair từ raw, không undo trên corrupted frame".

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| ------------------------------------ | ------------------------------------ | ---------------------------- |
| Truy ngược `text_for_embedding` được ghép từ những cột nào, chốt danh sách 4 cột (`title`, `summary`, `authors_joined`, `categories_joined`) và báo lại nhóm | TV2 — `cleaning.py`; TV5 — thiết kế thí nghiệm | Thành hằng `FIELDS_INSIDE_EMBEDDING_TEXT`, corruption trên bất kỳ cột nào trong đó đều rebuild lại text (commit `2a62e46`) |
| Đọc `_extract_answer()` trong `retrieval/qa.py` để biết mỗi loại câu hỏi lấy đáp án từ field nào | TV2 — `testset.py` | Phát hiện loại câu hỏi `authors` không bị kịch bản nào chạm tới → bổ sung `swap_authors` |
| Bàn giao `corruption_log.json` ở dạng có `paper_ids` từng operation | TV5 — `corruption_flow.py`, `corruption_report.md` | TV5 quy được từng câu hỏi trượt về đúng kịch bản gây ra nó, thay vì chỉ báo tổng số dòng hỏng |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --------------------------- | ----------------------------- | ------------------------- | ----------------------- |
| Cài đặt 7 kịch bản corruption trên các pool dòng rời nhau | `corrupt_clean_dataframe` | 24 dòng → 23 dòng, 20 `paper_id` bị ảnh hưởng | `data/results/corruption_log.json` |
| Tính lại `age_days` sau khi đổi `published` | `_age_days` | 3 dòng vượt ngưỡng 180 ngày (467/492/554 ngày) | `data/quality/freshness_report_corrupted.json`: `stale_rows: 3/23`, `is_fresh: false` |
| Dựng lại `text_for_embedding` cho dòng đã đổi cột nguồn | `_rebuild_text_for_embedding` | 12/23 dòng được rebuild, ghi rõ trong log | Operation `rebuild_text_for_embedding` liệt kê đúng 12 `paper_id` |
| Bổ sung kịch bản "lỗi thầm lặng" `swap_authors` | commit `2a62e46` | 3 dòng bị gán nhầm tác giả, **không** check quality nào FAIL | `data/quality/corrupted_quality.json` vẫn PASS `title_not_null`, `paper_id_not_null`; nhưng q010 `token_f1` 1.0 → 0.0 |
| Đảm bảo corruption tái lập được | `RANDOM_SEED = 42` | Chạy lại cho ra đúng log đã commit | Chạy `corrupt_clean_dataframe` trên `papers_clean.csv` 2 lần: hai log trùng nhau và trùng `corruption_log.json` đã commit |

Nêu một output cụ thể mà phần việc của tôi tạo ra hoặc giúp xác minh:

`data/results/corruption_log.json`. Đây không chỉ là file "ghi lại đã làm gì" — nó là **cầu nối để quy trách nhiệm**. Mỗi operation ghi `type`, `rows_affected`, danh sách `paper_ids` thật sự bị đổi và `details` (ngày trước/sau, title trước/sau, tác giả trước/sau). Nhờ có `paper_ids` mà tôi ghép được log với `ground_truth_doc_ids` trong `corrupted_answers.json` và trả lời được câu hỏi mà bảng metric tổng không trả lời nổi: *kịch bản nào làm hỏng câu hỏi nào*. Toàn bộ bảng phân tích ở mục 8 dựng từ phép ghép này.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Phá dữ liệu thì dễ, nhưng phá **để đo được** thì không. Một hàm corruption viết ẩu sẽ rơi vào một trong ba bẫy, và cả ba đều làm hỏng kết luận của cả nhóm chứ không chỉ hỏng phần của tôi:

1. **Phá mà pipeline không thấy.** Đổi `published` nhưng quên tính lại `age_days` → freshness check đọc `age_days` nên vẫn báo `is_fresh: true`. Dữ liệu đã cũ 554 ngày mà dashboard vẫn xanh.
2. **Phá mà embedding không thấy.** Đổi `summary` hay `authors_joined` nhưng quên dựng lại `text_for_embedding` → ChromaDB nhúng cột `text_for_embedding` chứ không nhúng cột nguồn, nên vector vẫn là vector của dữ liệu sạch. Retrieval không hề suy giảm, và kết luận sẽ thành "corruption không ảnh hưởng gì" — sai hoàn toàn.
3. **Phá mà không biết mình đã phá gì.** Các kịch bản đè lên nhau, hoặc log ghi sai số dòng → không quy được tác động về nguyên nhân.

### Cách triển khai

**Bảy kịch bản, ba nhóm tác động.** Tôi không chọn kịch bản theo kiểu "cho nhiều loại lỗi cho phong phú", mà chọn sao cho mỗi tầng của pipeline đều có ít nhất một kịch bản tấn công vào nó:

| Kịch bản | Tỷ lệ dòng | Tầng bị tấn công | Dự kiến signal nào bắt được |
| --- | --: | --- | --- |
| `drop_latest_records` | 12% | Corpus — tài liệu biến mất | freshness (mất bài mới nhất) |
| `blank_summary` | 12% | Nội dung — mất hẳn thông tin | `summary_length` |
| `inject_noise` | 12% | Nội dung — nhiễu vào vector | không check nào |
| `truncate_title` | 12% | Định danh — hỏng exact lookup | không check nào |
| `stale_published_date` | 16% | Thời gian — đẩy lùi 400 ngày | `freshness` |
| `swap_authors` | 14% | Tính đúng đắn — gán nhầm tác giả | **không check nào** |
| `duplicate_rows` | 8% | Ràng buộc — trùng `paper_id` | `paper_id_unique` |

Ba kịch bản không có check nào bắt được là chủ ý: chúng chứng minh "quality check PASS" ≠ "dữ liệu đúng".

**Pool dòng không chồng lấn.** Sau khi drop, tôi shuffle index còn lại **một lần** với `random.Random(42)` rồi cho các kịch bản lần lượt `_take()` từ cùng một iterator. Mỗi dòng vì thế chỉ trúng đúng một kịch bản (17/21 dòng còn lại bị chọn, 4 dòng giữ sạch). Nếu để các kịch bản bốc độc lập, một dòng vừa bị xóa summary vừa bị cắt title thì không cách nào biết câu hỏi liên quan trượt vì lý do nào.

**Rebuild bằng string-replace, không ráp lại theo template.** `_rebuild_text_for_embedding` nhận danh sách cặp `(giá trị cũ, giá trị mới)` và thay ngay trên chuỗi gốc, chỉ ráp lại tối thiểu khi không tìm thấy chuỗi cũ. Lý do: nếu tôi tự ráp `f"{title}\n\n{summary}"` thì định dạng đã khác `cleaning.py`, và một phần khác biệt embedding giữa baseline với corrupted sẽ đến từ **đổi định dạng** chứ không từ nội dung hỏng — nhiễu biến số vào đúng thứ mình đang đo.

**Nhân bản dòng làm bước cuối.** Bản sao phải mang giá trị đã corrupt, nếu duplicate trước thì bản sao còn sạch trong khi bản gốc đã hỏng, và corpus có hai phiên bản mâu thuẫn của cùng một `paper_id` — một loại lỗi khác hẳn cái tôi định mô phỏng.

**Log tự nhất quán theo thiết kế.** `_operation()` suy ra `rows_affected` từ `len(paper_ids)` thay vì nhận hai tham số rời. Chi tiết ở mục 6.

### Input, output và contract

| Thành phần | Mô tả |
| ------------------------------ | ------------------------------------------- |
| Input | `df: pd.DataFrame` cleaned 10 cột của TV2 (`paper_id`, `title`, `summary`, `published`, `authors_joined`, `categories_joined`, `age_days`, `text_for_embedding`, `abs_url`, `pdf_url`); `output_log_path` do TV5 truyền từ `settings.paths.corruption_log` |
| Output | DataFrame corrupt **giữ nguyên 10 cột** (đã verify `list(df.columns) == list(corrupted.columns)`); ghi `corruption_log.json` |
| Module phụ thuộc | `core.utils` (`now_utc`, `write_json`), `pandas`, `random` — không import module nào của thành viên khác |
| Module sử dụng output | `pipelines/corruption_flow.py` (TV5) → `retrieval/index.py` (build collection `papers-corrupted`) → `observability/quality.py` (TV3) |
| Điều kiện lỗi cần xử lý | DataFrame rỗng (ghi log rỗng kèm note, không crash); `published` không parse được (`errors="coerce"` → bỏ qua dòng đó, `age_days = pd.NA`); hai paper vốn cùng tác giả (xoay vòng không tạo thay đổi → không ghi vào log); `text_for_embedding` rỗng sau khi thay chuỗi (giữ lại title, cuối cùng là `"corrupted-record"`, vì ChromaDB nhận document rỗng sẽ hỏng index) |

Ràng buộc quan trọng nhất tôi phải giữ: **không đổi số cột và không đổi tên cột**. Corrupted frame vẫn phải đi lọt qua `_build_documents()` của `index.py` để build được index — corruption phải làm dữ liệu *sai*, không phải làm pipeline *gãy*. Nếu pipeline gãy thì không có metric nào để so sánh, và cả thí nghiệm mất luôn ý nghĩa.

### Cách xác minh

```bash
# Toàn luồng (TV5 chạy, artifact đã commit)
uv run python script/run_corruption_flow.py

# Kiểm tra tính tái lập của riêng hàm tôi phụ trách
uv run python -c "
import sys, json, pandas as pd; sys.path.insert(0,'src')
from ingestion.corruption import corrupt_clean_dataframe
df = pd.read_csv('data/clean/papers_clean.csv')
a = corrupt_clean_dataframe(df, '/tmp/log_a.json')
b = corrupt_clean_dataframe(df, '/tmp/log_b.json')
key = lambda p: [(o['type'], o['rows_affected'], o['paper_ids']) for o in json.load(open(p))['operations']]
print('deterministic:', key('/tmp/log_a.json') == key('/tmp/log_b.json'))
print('khop log da commit:', key('/tmp/log_a.json') == key('data/results/corruption_log.json'))
print('giu nguyen 10 cot:', list(df.columns) == list(a.columns))
"
```

- **Kết quả mong đợi:** hai lần chạy cho ra corrupted dataset giống hệt nhau và giống log đã commit; DataFrame trả về giữ nguyên 10 cột; 3 dòng bị đẩy `age_days` vượt 180.
- **Kết quả thực tế:** `deterministic: True`, `khop log da commit: True`, `giu nguyen 10 cot: True`, 24 → 23 dòng. `age_days` lớn nhất sau corrupt: 467, 492, 554 (dòng sạch cao nhất là 175, vẫn dưới ngưỡng).
- **Artifact/log:** `data/results/corruption_log.json`, `data/clean/papers_clean_corrupted.{csv,json}`, `data/quality/corrupted_quality.json`, `data/quality/freshness_report_corrupted.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Bản đầu (`58bb76e`) có 6 kịch bản. Khi đối chiếu với `_extract_answer()` trong `retrieval/qa.py` — nơi quyết định câu hỏi nào lấy đáp án từ field nào — tôi thấy 4 câu hỏi loại `authors` đọc thẳng `metadata["authors_joined"]`, mà **không kịch bản nào của tôi chạm vào cột đó**. Nghĩa là dù corrupt nặng đến đâu, 1/4 bộ đề vẫn được đảm bảo đúng.
- **Các phương án đã cân nhắc:** (1) Giữ nguyên 6 kịch bản, chấp nhận loại `authors` miễn nhiễm. (2) Tăng tỷ lệ dòng của các kịch bản sẵn có để kéo metric xuống mạnh hơn. (3) Thêm kịch bản `swap_authors` — xoay vòng `authors_joined` giữa các paper, mô phỏng lỗi join sai khóa trong ETL.
- **Phương án đã chọn:** Phương án 3, kèm việc viết lại `_rebuild_text_for_embedding` cho nhận danh sách cặp `(cũ, mới)` thay vì hard-code title/summary.
- **Lý do:** Phương án 2 chỉ làm con số xấu đi chứ không thêm thông tin nào — cùng loại lỗi, nhiều dòng hơn. `swap_authors` thì thêm một **loại** lỗi mới, và là loại nguy hiểm nhất trong thực tế: dữ liệu không null, không rỗng, không trùng, đúng kiểu, đúng định dạng — nó chỉ *sai*. Đây là kịch bản duy nhất vượt qua được toàn bộ 7 quality check của TV3. Phần viết lại rebuild là bắt buộc đi kèm, vì `authors_joined` nằm trong `text_for_embedding`: đổi tác giả mà không rebuild thì vector vẫn giữ tác giả cũ và corruption chỉ hỏng nửa vời.
- **Bằng chứng quyết định phù hợp:** Trên 3 dòng bị swap, `corrupted_quality.json` **không có check nào FAIL vì lý do này** — 3 FAIL đều đến từ `paper_id_unique`, `summary_length`, `freshness`. Nhưng q010 (*"Who authored the paper 'Microsoft Azure artificial intelligence / machine learning hackathon…'"*) trả lời `Nawari O. Nawari, Oluwatoyin O. Lawal` thay vì `Janet L. Autrey, Lacey S. Duckworth, …`: `token_f1` 1.0 → **0.0**, LLM judge chấm **1/5**. Retrieval vẫn hit đúng tài liệu — agent lấy đúng bài, chỉ là bài đó đã mang tác giả của người khác. Đúng chân dung lỗi mà tôi muốn mô phỏng.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Không có exception. Log ghi ra tự mâu thuẫn:

```json
{
  "type": "swap_authors",
  "rows_affected": 0,
  "paper_ids": ["10.3390/buildings16132637", "10.21203/rs.3.rs-9770645/v1", "10.21079/11681/50309"]
}
```

`rows_affected: 0` nhưng lại liệt kê 3 `paper_id`. Kịch bản `stale_published_date` có cùng lỗi khi gặp `published` không parse được.

- **Lệnh hoặc bước tái hiện:** Chạy `corrupt_clean_dataframe` trên DataFrame giả trong scratchpad, trong đó các paper được chọn có `authors_joined` giống hệt nhau (dữ liệu giả tôi tạo bằng cách nhân bản một dòng).
- **Nguyên nhân gốc:** Hai kịch bản này có nhánh `continue` — bỏ qua dòng khi hoán đổi không tạo thay đổi, hoặc khi ngày không parse được. Nhưng `rows_affected` lấy `len(selected_indexes)` (số dòng được **chọn**) còn `paper_ids` lấy từ danh sách đã lọc (số dòng **thật sự đổi**). Hai con số đến từ hai nguồn khác nhau nên trôi khỏi nhau mỗi khi có dòng bị bỏ qua. Bản chất là lỗi thiết kế API: `_operation` bản đầu nhận `rows_affected` và `paper_ids` như hai tham số độc lập, tức là *cho phép* người gọi viết sai.
- **Cách xử lý:** Gom việc tạo log vào helper `_operation(kind, description, paper_ids, details)` và suy `rows_affected = len(paper_ids)` bên trong ([corruption.py:61-80](../src/ingestion/corruption.py#L61-L80)). Đồng thời sửa hai kịch bản để tích lũy `stale_applied` / `swap_applied` — chỉ những dòng thật sự bị đổi — thay vì log nguyên danh sách được chọn. Sau sửa, hai con số **không thể** lệch nhau vì chỉ còn một nguồn sự thật.
- **Cách xác minh sau khi sửa:** Chạy lại trên dữ liệu giả trùng tác giả: `rows_affected` xuống đúng 0 và `paper_ids` cũng rỗng. Trên dữ liệu thật: `swap_authors` báo 3 dòng với 3 `paper_id`, `stale_published_date` báo 3 dòng với 3 `paper_id`, và `distinct_paper_ids_affected: 20` = 3 (drop) + 17 (pool) khớp đúng phép cộng thủ công.
- **Điều học được:** Lỗi này không làm chương trình dừng, không làm test đỏ — nó chỉ làm **báo cáo nói sai sự thật**. Nếu lọt, mục 8 của tôi sẽ dựa trên số dòng không đúng và mọi phân tích phía sau lệch theo, mà không ai có cách nào phát hiện. Bài học cụ thể: khi hai trường trong một artifact phải khớp nhau, đừng kiểm tra bằng kỷ luật — hãy dựng API sao cho người gọi *không viết sai được*. Rộng hơn: artifact quan sát cũng là dữ liệu, và nó cũng cần được kiểm tra tính nhất quán y như dữ liệu nghiệp vụ.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

**1. Dữ liệu đi từ Crossref đến vector index như thế nào?** `crossref.py` gọi endpoint `/works` với filter `from-pub-date` (suy từ ngưỡng 180 ngày) và `has-abstract`, lưu **nguyên payload** vào `crossref_response.json` rồi parse thành `PaperRecord` lưu ở `crossref_records.json`. `cleaning.py` chuẩn hóa whitespace, bóc thẻ JATS trong abstract, parse ngày, tính `age_days`, ghép `text_for_embedding` từ title + summary + authors + categories, dedup theo `paper_id`. `index.py` đưa **riêng cột `text_for_embedding`** qua MiniLM-L6-v2 thành vector 384 chiều và nạp vào ChromaDB, các cột còn lại đi kèm dưới dạng metadata. Chi tiết cuối cùng này là chi tiết quan trọng nhất với vai của tôi: cột nào không nằm trong `text_for_embedding` thì phá nó cũng không đổi được vector, chỉ đổi được câu trả lời qua đường metadata.

**2. Evaluation set và ground-truth document IDs dùng để đo ra sao?** Mỗi câu hỏi có `ground_truth` (đáp án lấy từ clean data) và `ground_truth_doc_ids` (`paper_id` chứa đáp án). `retrieval_hit_rate` xét giao giữa `retrieved_doc_ids` với `ground_truth_doc_ids` — đo tầng **tìm đúng tài liệu**; `mean_token_f1` so từ giữa câu trả lời và `ground_truth` — đo tầng **nội dung bên trong tài liệu**. Tách hai tầng cho phép chẩn đoán chính xác, và corruption của tôi là phép thử cho việc tách đó: `drop_latest_records` đánh vào tầng một, `swap_authors` đánh vào tầng hai mà tầng một vẫn xanh.

**3. Quality checks khác freshness monitoring ở điểm nào?** Quality checks hỏi "dữ liệu có đúng dạng không" — đủ dòng, `paper_id` không null/không trùng, title không rỗng, summary đủ 40 ký tự. Chúng chạy được trên một snapshot đứng yên và cho cùng kết quả bất kể chạy hôm nay hay năm sau. Freshness hỏi "dữ liệu có còn kịp thời không" — so `age_days` với ngưỡng 180 ngày, và là chiều **duy nhất phụ thuộc thời điểm chạy**: cùng một dataset hôm nay Fresh, sáu tháng sau tự động Stale mà không ai sửa gì. Chính vì freshness đọc `age_days` chứ không đọc `published` mà tôi phải tính lại `age_days` ngay trong kịch bản `stale_published_date` — bỏ bước đó thì đẩy ngày lùi 400 ngày vẫn không làm signal nào nhúc nhích.

**4. Vì sao phải dùng cùng test set cho cả ba trạng thái?** Vì đây là thí nghiệm có đối chứng: chỉ được đổi một biến (chất lượng dữ liệu), mọi thứ khác phải giữ nguyên. Nếu sinh lại bộ đề trên dữ liệu đã hỏng thì `ground_truth` cũng được trích **từ chính dữ liệu hỏng**, agent trả lời sai vẫn được chấm đúng, và corruption của tôi trông như vô hại. Cụ thể với q010: bộ đề đóng băng giữ `ground_truth` là tác giả thật, nên câu trả lời sai bị bắt; nếu sinh lại, `ground_truth` sẽ thành đúng tác giả đã bị swap và câu đó được 1.0 điểm.

**5. Repair được xem là thành công dựa trên artifact và metric nào?** Ba tầng bằng chứng. Tầng dữ liệu, mạnh nhất: `corruption_summary.json` cho `missing_after_repair: []`, `unexpected_after_repair: []`, `fully_restored: true` — tập `paper_id` sau repair khớp baseline chính xác. Tầng signal: `repaired_quality.json` 7/7 PASS, `freshness_report_repaired.json` `is_fresh: true` với `oldest_published` trở lại `2026-02-12` (corrupted là `2025-01-29`). Tầng metric: cả bốn chỉ số RAG về đúng 1.0/1.0/1.0/5.0. Điều làm repair đáng tin là nó dựng lại từ `crossref_records.json` qua `build_clean_dataframe` — cùng đường đi với baseline, hoàn toàn không đụng tới `corruption.py`, nên nó là một phép dựng lại độc lập chứ không phải một phép "undo" có thể vô tình che lỗi.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| ---------------------- | -------: | --------: | -------: | ------------------------- |
| `retrieval_hit_rate` | 1.0000 | 0.7500 | 1.0000 | 4/16 câu mất hit — 3 do `drop_latest_records`, 1 do `truncate_title` |
| `mean_token_f1` | 1.0000 | 0.5900 | 1.0000 | Tụt sâu hơn hit rate (−0.41 vs −0.25): nhiều câu lấy đúng tài liệu nhưng nội dung bên trong đã hỏng |
| `judge_accuracy` | 1.0000 | 0.6250 | 1.0000 | 6/16 câu bị chấm dưới 5 — trùng khớp danh sách câu có `token_f1` tụt, hai thang đo độc lập cùng chỉ một hướng |
| `mean_judge_score` | 5.0000 | 3.6875 | 5.0000 | Sáu câu hỏng được chấm 1–2 điểm, không có câu nào "hơi sai" |
| Quality checks | PASS 7/7 | FAIL 3/7 | PASS 7/7 | FAIL: `paper_id_unique` (2 trùng), `summary_length` (3 dòng < 40 ký tự), `freshness` (3/23 quá hạn) |
| Freshness status | Fresh | Stale | Fresh | `oldest_published` 2026-02-12 → 2025-01-29; `latest_published` 2026-08-01 → 2026-07-03 |

### Quy tác động về từng kịch bản

Bảng dưới ghép `paper_ids` trong `corruption_log.json` với `ground_truth_doc_ids` trong `corrupted_answers.json` — đây là phân tích riêng của tôi, không có trong báo cáo nhóm:

| Kịch bản | Dòng | Câu hỏi trúng tài liệu bị hỏng | Mất hit | `token_f1` tụt |
| --- | --: | --- | --: | --- |
| `drop_latest_records` | 3 | q003, q008, q011 | **3** | 1.0 → 0.0 / 0.4 / 0.0 |
| `truncate_title` | 3 | q004, q006, q009 | **1** (q009) | q009: 1.0 → 0.04 |
| `blank_summary` | 3 | q001, q016 | 0 | q001: 1.0 → 0.0 |
| `stale_published_date` | 3 | q007, q013 | 0 | q007: 1.0 → 0.0 |
| `swap_authors` | 3 | q010, q015 | 0 | q010: 1.0 → 0.0 |
| `inject_noise` | 3 | q002, q012 | 0 | không câu nào |
| `duplicate_rows` | 2 | — | 0 | không câu nào |

### Kết luận từ số liệu

1. **`drop_latest_records` xóa 3 bài mới nhất + `stale_published_date` đẩy 3 bài lùi 400 ngày** → `freshness_report_corrupted.json` chuyển `is_fresh: false` với `stale_rows: 3/23`, `duplicate_rows` làm `paper_id_unique` FAIL, `blank_summary` làm `summary_length` FAIL → `retrieval_hit_rate` 1.0 → 0.75 và `mean_token_f1` 1.0 → 0.59.

2. **Repair dựng lại 24 record từ `crossref_records.json`** (không đụng file của tôi) → `corruption_summary.json` cho `fully_restored: true`, quality trở lại 7/7 PASS, freshness trở lại Fresh → cả bốn chỉ số RAG phục hồi **100%** về đúng giá trị baseline. Phục hồi trọn vẹn là điều đoán trước được: mọi kịch bản của tôi chỉ tác động lên cleaned dataset, còn raw snapshot bất biến — nếu tôi được phép corrupt cả `data/raw/` thì repair sẽ không thể hoàn hảo như vậy.

Corruption nào ảnh hưởng rõ nhất và vì sao?

`drop_latest_records` — 3/4 câu mất hit đều thuộc kịch bản này. Lý do triệt để: tài liệu không còn trong index thì không thuật toán retrieval nào lấy ra được, và không tầng nào phía dưới cứu được. Các kịch bản khác *làm giảm chất lượng* tín hiệu, kịch bản này *xóa* tín hiệu. Xếp thứ hai là `truncate_title`, và nó thú vị hơn về mặt cơ chế: `retrieval/qa.py` có đường exact lookup theo title trong dấu nháy đơn, cắt title còn 12 ký tự (`"Hybrid Retrieval-Augmented Generation: …"` → `"Hybrid Retri"`) làm đường tắt đó đứt, câu q009 rơi xuống thuần semantic search và lấy nhầm một bài RAG khác — `token_f1` còn 0.04.

Kết quả nào khác với kỳ vọng ban đầu?

**`inject_noise` không gây thiệt hại nào cả** — không mất hit, không tụt `token_f1` trên cả hai câu liên quan (q002, q012). Tôi kỳ vọng ngược lại, vì nó phá trực tiếp `summary`, tức là phá vào đúng chuỗi được đưa vào MiniLM.

Giả thuyết ban đầu của tôi là do corpus quá nhỏ: 23 tài liệu với `top_k = 4` nghĩa là mỗi truy vấn lấy về ~1/6 corpus, vector lệch đi vẫn dễ lọt top-4. Nhưng khi đối chiếu từng câu, tôi thấy lý do thật khác và cụ thể hơn: **hai câu trúng vào 3 dòng bị nhiễu lại là câu loại `authors` (q002) và `categories` (q012)**, mà theo `_extract_answer()` thì hai loại này đọc `authors_joined` / `categories_joined` từ metadata — không đọc `summary`. Nhiễu nằm ở chỗ mà câu hỏi không nhìn tới. Cùng cơ chế đó giải thích vì sao `blank_summary` chỉ hỏng q001 (loại `summary`) mà không hỏng q016 (loại `categories`), và `stale_published_date` chỉ hỏng q007 (loại `date`) mà không hỏng q013.

Nói cách khác: **tác động của corruption không phụ thuộc vào việc nó phá nặng đến đâu, mà phụ thuộc vào việc nó có phá đúng field mà câu hỏi đọc hay không.** Đây là hệ quả trực tiếp của việc pool dòng không chồng lấn — nếu các kịch bản đè lên nhau, tôi đã không tách được kết luận này ra khỏi nhiễu.

Cách kiểm chứng dứt điểm giả thuyết corpus nhỏ: giữ nguyên seed, nâng `max_results` lên vài trăm rồi đo lại; nếu hit rate của các câu bị `inject_noise` tụt thì kích thước corpus đúng là yếu tố che giấu.

Một quan sát nhỏ về `duplicate_rows`: không câu nào bị nó làm hỏng đáp án, nhưng ở q008 danh sách `retrieved_doc_ids` là `[..., "10.70121/001c.158711", "10.70121/001c.158711", ...]` — bản sao chiếm **hai** trong bốn ô top-k. Nó không làm sai câu trả lời trong bài này, nhưng cho thấy trùng lặp âm thầm bào mòn độ đa dạng ngữ cảnh: cửa sổ 4 tài liệu thực chất chỉ còn 3.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. **Về data pipeline:** Trong một pipeline, cột được *lưu* và cột được *dùng* là hai thứ khác nhau, và bug nghiêm trọng nhất nằm ở khoảng cách giữa chúng. `published` được lưu nhưng freshness đọc `age_days`; `summary` được lưu nhưng ChromaDB nhúng `text_for_embedding`. Sửa cột nguồn mà không cập nhật cột dẫn xuất thì dữ liệu đã hỏng nhưng hệ thống vẫn báo bình thường — không phải vì check yếu, mà vì check đang nhìn vào một bản sao đã cũ. Với vai người *cố ý* phá dữ liệu, tôi buộc phải hiểu chuỗi phụ thuộc này chính xác hơn cả khi viết code sạch, vì phá sai chỗ thì không đo được gì.

2. **Về data quality/observability:** Bộ check chỉ bắt được đúng những chiều nó được viết ra để bắt. Kịch bản `swap_authors` của tôi phá 3 dòng, khiến agent trả lời sai hoàn toàn tác giả (`token_f1` 0.0, judge 1/5), mà **cả 7 check đều PASS** — vì dữ liệu vẫn không null, không rỗng, không trùng, đúng kiểu. "Tất cả check đều xanh" chỉ có nghĩa là "không có lỗi thuộc loại tôi đã nghĩ tới". Completeness/Uniqueness/Timeliness kiểm được từ nội tại dữ liệu; Accuracy thì không — nó bắt buộc phải đối chiếu với nguồn, nên là chiều đắt nhất và cũng là chiều hay bị bỏ nhất.

3. **Về ảnh hưởng của dữ liệu đến RAG agent:** Dữ liệu hỏng không làm hệ thống báo lỗi. Không exception, không test đỏ, pipeline chạy xanh từ đầu đến cuối và agent trả lời trôi chảy, đúng ngữ pháp, đúng định dạng — chỉ là sai nội dung. q010 trả về một cái tên hoàn toàn có thật, của một bài báo hoàn toàn có thật, chỉ là không phải bài được hỏi. Không có cách nào nhìn thấy loại lỗi này ngoài việc đo bằng số trên một bộ đề cố định.

### Nếu có thêm thời gian

Tôi sẽ đề xuất với TV3 thêm một check chiều **Accuracy** để bịt đúng lỗ hổng mà `swap_authors` chui qua: đối chiếu `authors_joined` của cleaned dataset với trường `authors` trong `crossref_records.json` theo `paper_id`, dòng nào lệch thì FAIL. Raw snapshot đóng vai ground truth nên check này khả thi mà không cần gọi API.

Cách đo cải thiện rất rõ ràng vì đã có sẵn kỳ vọng: chạy lại `run_corruption_flow.py` với seed 42, check mới phải bắt **đúng 3 dòng** — trùng khớp danh sách `paper_ids` của operation `swap_authors` trong `corruption_log.json` — và `corrupted_quality.json` phải chuyển từ 3 FAIL lên 4 FAIL, trong khi `baseline_quality.json` và `repaired_quality.json` vẫn phải 100% PASS (nếu chúng cũng FAIL thì check bị dương tính giả). Đây là chỗ duy nhất trong bài mà một loại lỗi lọt qua toàn bộ chốt chặn observability, nên vá nó có giá trị cao nhất trên mỗi dòng code bỏ ra. Nếu còn thời gian nữa, tôi sẽ thêm kịch bản `corrupt_paper_id` (đổi định danh) để kiểm tra xem repair có còn `fully_restored` khi chính khóa join bị hỏng — tôi ngờ là không, và đó sẽ là giới hạn thật của cơ chế repair hiện tại.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Trần Văn Hiếu
**Ngày xác nhận:** 2026-08-06

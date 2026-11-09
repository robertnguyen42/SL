# Bản tin Di trú

Web tự cập nhật tin di trú Úc / Mỹ / Canada, nhóm theo tuần. Miễn phí 100% (GitHub Actions + GitHub Pages).

## Cách hoạt động
1. `fetch_news.py` đọc các nguồn trong `sources.json` → ghi `docs/data/news.json`
2. GitHub Actions chạy script mỗi 30 phút, commit nếu có tin mới
3. GitHub Pages phục vụ thư mục `docs/`; trang web tự kiểm tra tin mới mỗi 60 giây

## Chạy thử trên máy
```
python3 fetch_news.py
python3 -m http.server 8000 -d docs
```
Mở http://localhost:8000

## Đưa lên mạng (1 lần)
1. Tạo repo mới trên github.com (Public), đẩy thư mục này lên
2. Settings → Pages → Source: *Deploy from a branch* → branch `main`, folder `/docs`
3. Settings → Actions → General → Workflow permissions: *Read and write*
4. Link: `https://<tên-github>.github.io/<tên-repo>/`

## Từ khoá: Nước → Loại visa (`keywords.json`)
- Cấp 1 `country`: từ nhận diện nước (Úc, Australia, USCIS…)
- Cấp 2 `visas`: mỗi loại visa có `name` (tên hiển thị), `kw` (từ khoá gắn nhãn), `q` (câu tìm Google News riêng, để `""` nếu không cần)
- Số thuần (`482`) chỉ khớp khi có "visa/subclass/diện" đi kèm; chữ viết hoa ngắn (`TSS`, `CRS`) khớp đúng hoa thường
- Sửa xong chạy lại `fetch_news.py` là toàn bộ tin cũ được gắn nhãn lại
- Tin rác: thêm cụm từ vào `EXCLUDE` trong `fetch_news.py`

## Thêm / bớt nguồn
Sửa `sources.json`. `type: "official"` = nguồn chính phủ (hiện tóm tắt), `type: "news"` = báo chí (lọc theo từ khoá trong `fetch_news.py`).

## Tóm tắt tuần bằng AI (`summarize.py`) — ĐANG TẮT (chưa dùng chi phí API)
- Chạy 8:00 sáng thứ Hai (giờ VN) qua `.github/workflows/summary.yml`, hoặc bấm *Run workflow* để chạy ngay
- Claude đọc tin 7 ngày qua, chọn Top 5 thay đổi, viết tiếng Việt → `docs/data/summary.json` (lưu trữ từng tuần trong `docs/data/summaries/`)
- Cần secret `ANTHROPIC_API_KEY` trong Settings → Secrets and variables → Actions. Chưa có thì bước này tự bỏ qua
- Chi phí ước tính: khoảng 0,05 USD/tuần

## Email bản tin (`notify.py`)
- `.github/workflows/notify.yml` chạy 8:30 sáng mỗi ngày (giờ VN); `notify.py` chỉ gửi khi đã đủ 3 ngày kể từ lần trước (`docs/data/notify_state.json`)
- Nội dung: tin mới của Mỹ, Úc, Châu Âu (đổi trong `COUNTRIES`), nhóm theo diện visa, tối đa 3 tin mỗi diện, 15 tin mỗi nước
- Secrets cần có: `SMTP_USER` (email gửi), `SMTP_PASS` (App Password), `EMAIL_TO` (người nhận, cách nhau dấu phẩy). Danh sách người nhận chỉ nằm trong secrets, không ghi vào code
- Xem trước không gửi: `python3 notify.py --preview preview.html`. Gửi ngay: Actions → Gửi email bản tin → Run workflow

## AI phân loại Siết / Nới (`classify.py`) — ĐANG TẮT (chưa dùng chi phí API)
- Chạy trong workflow cập nhật tin; gom lô (>= 40 tin chờ hoặc chờ quá 6 giờ) rồi gọi Claude một lần
- Claude quyết định: có phải tin thay đổi chính sách không, và chính sách bị **siết** hay **nới** → lưu `docs/data/ai_labels.json`
- Tin chưa được AI phân loại vẫn dùng nhãn theo từ khoá (`_uu_tien` trong `keywords.json`)
- Dùng chung secret `ANTHROPIC_API_KEY` với tóm tắt tuần. Lỗi AI không chặn việc cập nhật tin

## Keyword từ Google Sheet (`sync_keywords.py`)
- Nguồn: sheet "SL | KEYWORD CẬP NHẬT THÔNG TIN ĐỊNH CƯ", Sheet1, cột QUỐC GIA / DẠNG VISA / KEYWORD
- Mỗi lần cập nhật tin (30 phút), GitHub tải sheet → `sheet_keywords.csv`. Sheet phải để "Bất kỳ ai có đường liên kết: Người xem"; chưa chia sẻ thì dùng bản đã lưu
- Trang có 2 cấp lọc: **Nhóm** theo sheet (Chung các loại / Tay nghề / Đầu tư / Khác) → **Loại visa** chi tiết (`keywords.json`, trường `nhom` nối loại visa với nhóm)
- Mỗi nhóm trong sheet tự sinh truy vấn Google News (6 keyword/truy vấn). Keyword quá chung bị bỏ qua: job, regional, SBS

## Phân tầng nguồn tin (`source_tiers.json`)
- Mỗi tin được gắn `tier`: `gov` (cơ quan chính phủ), `press` (báo chí), `agency` (công ty di trú, hãng luật, trang dịch vụ visa)
- Điểm ưu tiên: chính phủ +3, công ty di trú −1,5 (cộng với điểm tin chính sách, diện chính, tiếng Việt)
- Sửa danh sách tên nguồn trong `source_tiers.json`, lần cập nhật sau áp dụng cho toàn bộ tin

## Dịch tiếng Việt (`translate.py`) — Claude Opus 5.5, chạy mỗi 30 phút khi có secret ANTHROPIC_API_KEY
- Dịch tiêu đề (và tóm tắt nếu có) của tin tiếng Anh sang tiếng Việt, giữ nguyên thuật ngữ (EB-5, 482, Express Entry, Golden Visa…)
- Kết quả lưu `docs/data/translations.json`; `fetch_news.py` gắn `title_vi` / `summary_vi` vào tin; trang web hiện tiếng Việt kèm "Bản gốc"
- Mỗi tin chỉ dịch một lần. Biến môi trường: `TRANSLATE_MODEL`, `TRANSLATE_DAYS`, `TRANSLATE_LIMIT`
- Đã có trong `update.yml`; chỉ dịch tin lấy về từ 09/11/2026 (`TRANSLATE_SINCE`), tối đa 300 tin mỗi lần. Từ 09/11/2026 không lấy tin từ báo tiếng Việt nữa (`DROP_VI` trong `fetch_news.py`)

## Chương trình SI (`programs.json`) — mặc định chỉ hiện tin thuộc chương trình SI
- Lập từ file "MATRIX SẢN PHẨM ĐỊNH CƯ": Mỹ EB-5 / EB-3 / EB-1C / L-1 (+ Visa Bulletin); Úc 482 / 494-191 / 186 / 858 NIV (+ Migration Program);
  Canada Start-up Visa / PNP / Express Entry / Levels Plan; châu Âu Golden Visa & quốc tịch đầu tư; NZ Active Investor Plus;
  UAE Golden Visa & Freezone; quốc tịch châu Âu (Thổ Nhĩ Kỳ, Pháp, Hungary, Croatia, Malta); NZ Business Investor; Caribe CBI (Grenada, St Kitts & Nevis, Antigua & Barbuda, Saint Lucia, Dominica)
- Tin khớp chương trình: gắn `programs`, `si=true`, cộng 2 điểm ưu tiên; translate.py chỉ dịch tin SI
- Trang web mặc định lọc "Tin chính sách" + chương trình SI; có nút "Hiện cả tin ngoài chương trình SI"
- translate.py đồng thời để Claude đánh giá tin có phải thay đổi chính sách không và hướng siết/nới (ghi `ai_labels.json`)
- Visa du lịch (Mỹ, Úc, Canada, Schengen, NZ, UAE): chỉ lấy tin liên quan công dân Việt Nam / Đông Nam Á (trường `cung`),
  hoặc thay đổi áp dụng mọi quốc tịch (trường `toan_cau`, vd phí visa) mà không chỉ nói về công dân nước khác (trường `tru`)
- Từ 09/11/2026 trang chính (`docs/index.html`) dùng giao diện thư viện mới; `preview.html` chuyển hướng về trang chính

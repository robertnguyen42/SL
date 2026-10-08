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

## Tóm tắt tuần bằng AI (`summarize.py`)
- Chạy 8:00 sáng thứ Hai (giờ VN) qua `.github/workflows/summary.yml`, hoặc bấm *Run workflow* để chạy ngay
- Claude đọc tin 7 ngày qua, chọn Top 5 thay đổi, viết tiếng Việt → `docs/data/summary.json` (lưu trữ từng tuần trong `docs/data/summaries/`)
- Cần secret `ANTHROPIC_API_KEY` trong Settings → Secrets and variables → Actions. Chưa có thì bước này tự bỏ qua
- Chi phí ước tính: khoảng 0,05 USD/tuần

## Email bản tin (`notify.py`)
- `.github/workflows/notify.yml` chạy 8:30 sáng mỗi ngày (giờ VN); `notify.py` chỉ gửi khi đã đủ 3 ngày kể từ lần trước (`docs/data/notify_state.json`)
- Nội dung: tin mới của Mỹ, Úc, Châu Âu (đổi trong `COUNTRIES`), nhóm theo diện visa, tối đa 3 tin mỗi diện, 15 tin mỗi nước
- Secrets cần có: `SMTP_USER` (email gửi), `SMTP_PASS` (App Password), `EMAIL_TO` (người nhận, cách nhau dấu phẩy). Danh sách người nhận chỉ nằm trong secrets, không ghi vào code
- Xem trước không gửi: `python3 notify.py --preview preview.html`. Gửi ngay: Actions → Gửi email bản tin → Run workflow

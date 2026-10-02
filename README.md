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

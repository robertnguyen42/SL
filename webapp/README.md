# Web app nội bộ "Bản tin Di trú" (Google Apps Script)

- Chỉ tài khoản @si.im xem được (`appsscript.json`: `access: DOMAIN`, chạy dưới quyền người deploy).
- Dữ liệu: `docs/data/news_si.json` do GitHub Actions xuất mỗi 30 phút (`export_slim.py`); web app đọc qua UrlFetchApp, đệm 5 phút.
- Facebook đối thủ: Google Sheet nội bộ, ID lưu ở Script Property `LIB_FB_SHEET_ID` (tạo bằng hàm `Lib_setupFacebookSheet`, chạy 1 lần).
- Gộp vào app Case Management sau này: chép `Library.js` + `LibraryPage.html`, bỏ `doGet` trong `Library.js`, thêm `?view=library` gọi `Lib_render(e)`.
- `LibraryPage.html` lấy từ `docs/index.html`, chỉ khác phần tải dữ liệu (google.script.run) và tham số trên địa chỉ trang.

Cập nhật code: `clasp push` trong thư mục `webapp/`, rồi `clasp deploy -i <deploymentId>` để giữ nguyên link.

## Đang chạy
- Chủ sở hữu: daniel.do@si.im
- Script ID: `1hZTMEPBaLA0wzwRiO9jNpnG6h7utRAjkKhamA7bso09UfIObDeoNlF3c` (editor: https://script.google.com/d/1hZTMEPBaLA0wzwRiO9jNpnG6h7utRAjkKhamA7bso09UfIObDeoNlF3c/edit)
- Deployment: `AKfycbwm7zZ_AB0b5BMIw3YssAyjSanun2PyHqr4m-6MLzKAmm_ptIH_3ibMQlwCjvWj_q04LA`
- Link: https://script.google.com/a/macros/si.im/s/AKfycbwm7zZ_AB0b5BMIw3YssAyjSanun2PyHqr4m-6MLzKAmm_ptIH_3ibMQlwCjvWj_q04LA/exec
- Cập nhật giữ nguyên link: `clasp push` rồi `clasp create-deployment -i AKfycbwm7zZ_AB0b5BMIw3YssAyjSanun2PyHqr4m-6MLzKAmm_ptIH_3ibMQlwCjvWj_q04LA`

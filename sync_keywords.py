#!/usr/bin/env python3
"""Tải keyword từ Google Sheet "SL | KEYWORD CẬP NHẬT THÔNG TIN ĐỊNH CƯ" (Sheet1) -> sheet_keywords.csv.
Sheet cần chia sẻ "Bất kỳ ai có đường liên kết: Người xem" (hoặc Xuất bản lên web) thì máy chủ GitHub mới đọc được.
Tải lỗi hoặc nội dung lạ thì giữ nguyên bản cũ, không làm hỏng trang."""
import csv, io, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "sheet_keywords.csv"
SHEET_ID = "1okN5tfi0hJz1tjXgMNiJd62YmQNkes9jdPG_YpyzUgc"
URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=0"


def main():
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (DiTruNewsBot)"})
        with urllib.request.urlopen(req, timeout=30) as r:
            if "text/csv" not in r.headers.get("Content-Type", ""):
                raise ValueError("sheet chưa được chia sẻ công khai (Google trả về trang đăng nhập)")
            text = r.read().decode("utf-8")
    except Exception as e:
        print(f"Không tải được sheet ({e}). Giữ keyword hiện có.")
        return
    rows = list(csv.reader(io.StringIO(text)))
    if not any("KEYWORD" in c.upper() for row in rows[:5] for c in row) or len(rows) < 5:
        print("Sheet không có cột KEYWORD như mong đợi. Giữ keyword hiện có.", file=sys.stderr)
        return
    if OUT.exists() and OUT.read_text("utf-8") == text:
        print("Keyword không đổi.")
        return
    OUT.write_text(text, "utf-8")
    print(f"Đã cập nhật keyword từ sheet ({len(rows)} dòng).")


if __name__ == "__main__":
    main()

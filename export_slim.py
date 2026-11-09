#!/usr/bin/env python3
"""Xuất docs/data/news_si.json — bản dữ liệu gọn cho web app nội bộ (Apps Script, thư mục webapp/).
Gồm: toàn bộ tin thuộc chương trình SI (120 ngày) + tin chính sách ngoài chương trình SI trong 30 ngày gần nhất
(cho nút "Hiện cả tin ngoài chương trình SI"). Chỉ giữ các trường giao diện cần dùng, để web app tải nhanh."""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

DATA = Path(__file__).parent / "docs" / "data"
FIELDS = ["id", "title", "title_vi", "summary", "summary_vi", "link", "publisher", "country", "type", "tier",
          "published", "fetched", "programs", "groups", "policy", "direction", "lang", "score", "si"]
NON_SI_DAYS = 30


def main():
    news = json.loads((DATA / "news.json").read_text("utf-8"))
    now = datetime.now(timezone.utc)
    keep = [i for i in news["items"] if i.get("si") or
            (i.get("policy") and now - datetime.fromisoformat(i["published"]) < timedelta(days=NON_SI_DAYS))]
    items = [{k: i[k] for k in FIELDS if i.get(k) not in (None, "", [], False)} for i in keep]
    tax = news.get("taxonomy", {})
    out = {"updated": news["updated"], "taxonomy": {"_programs": tax.get("_programs", {})}, "items": items}
    (DATA / "news_si.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), "utf-8")
    print(f"news_si.json: {len(items)} tin, {(DATA / 'news_si.json').stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Tóm tắt tuần bằng Claude: đọc tin 7 ngày qua trong docs/data/news.json
-> docs/data/summary.json (bản mới nhất) + docs/data/summaries/<năm>-W<tuần>.json (lưu trữ).
Cần biến môi trường ANTHROPIC_API_KEY; thiếu thì bỏ qua, không báo lỗi."""
import json, os, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Literal

ROOT = Path(__file__).parent
DATA = ROOT / "docs" / "data"
MODEL = "claude-opus-5-5"
TOP_N = 5

SYSTEM = """Bạn là biên tập viên bản tin di trú nội bộ của một công ty tư vấn định cư và bất động sản quốc tế tại Việt Nam.
Người đọc là đội tư vấn: họ cần biết tuần này có thay đổi chính sách nào ảnh hưởng tới khách hàng Việt Nam.

Từ danh sách tin trong tuần, chọn đúng {n} thay đổi quan trọng nhất. Ưu tiên:
1. Thay đổi chính sách, luật, phí, hạn mức, thời gian xử lý, lịch visa (Visa Bulletin), kết quả rút hồ sơ (Express Entry draw).
2. Nguồn chính phủ (type=official) hơn báo chí; tin được nhiều báo cùng đưa hơn tin lẻ.
3. Diện visa người Việt hay dùng: du học, tay nghề, đầu tư (EB-5, NIV/188), bảo lãnh gia đình.
Bỏ qua tin hình sự cá nhân, tin người nổi tiếng, tin trùng lặp. Gộp các tin cùng một sự kiện thành một mục.

Viết tiếng Việt, câu ngắn, rõ, không phóng đại. Chỉ dùng thông tin có trong tiêu đề/tóm tắt được cung cấp;
nếu tiêu đề chưa đủ chi tiết (ví dụ chưa rõ ngày hiệu lực) thì nói rõ là cần kiểm tra nguồn, không tự suy đoán con số."""


def week_items(news, days=7):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    items = [i for i in news["items"] if datetime.fromisoformat(i["published"]) >= cutoff]
    return items[:600]  # đủ cho 1 tuần; news.json đã sắp xếp mới nhất trước


def build_prompt(items, taxonomy):
    visa_names = {c: t["visas"] for c, t in taxonomy.items()}
    lines = []
    for n, i in enumerate(items):
        visas = ", ".join(visa_names.get(i["country"], {}).get(v, v) for v in i.get("visas", []))
        line = f'[{n}] {i["published"][:10]} | {i["country"]} | {i["type"]} | {visas or "-"} | {i["title"]}'
        if i.get("summary"):
            line += f' || {i["summary"][:200]}'
        lines.append(line)
    return ("Danh sách tin tuần này (định dạng: [số] ngày | nước | loại nguồn | diện visa | tiêu đề || tóm tắt):\n\n"
            + "\n".join(lines))


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Chưa có ANTHROPIC_API_KEY, bỏ qua tóm tắt tuần.")
        return

    import anthropic
    from pydantic import BaseModel, Field

    news = json.loads((DATA / "news.json").read_text("utf-8"))
    items = week_items(news)
    if len(items) < 5:
        print(f"Chỉ có {len(items)} tin trong tuần, bỏ qua.")
        return
    countries = tuple(news["taxonomy"].keys())

    class Highlight(BaseModel):
        headline: str = Field(description="Tiêu đề tiếng Việt, tối đa 15 từ")
        detail: str = Field(description="2-3 câu: điều gì thay đổi, từ khi nào, con số chính")
        impact: str = Field(description="1 câu: ai bị ảnh hưởng / tư vấn viên nên lưu ý gì")
        country: Literal[countries]  # type: ignore[valid-type]
        visas: List[str] = Field(description="Mã diện visa liên quan, lấy từ danh sách mã được cung cấp")
        sources: List[int] = Field(description="Số thứ tự [n] của 1-3 tin nguồn tốt nhất")

    class WeeklySummary(BaseModel):
        overview: str = Field(description="1-2 câu tổng quan cả tuần")
        highlights: List[Highlight]

    codes = "; ".join(f"{c}: " + ", ".join(t["visas"].keys()) for c, t in news["taxonomy"].items())
    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "medium"},
        system=SYSTEM.format(n=TOP_N),
        messages=[{"role": "user",
                   "content": build_prompt(items, news["taxonomy"]) + f"\n\nMã diện visa hợp lệ — {codes}"}],
        output_format=WeeklySummary,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        print(f"Claude không trả kết quả (stop_reason={response.stop_reason}), giữ bản tóm tắt cũ.", file=sys.stderr)
        return

    result = response.parsed_output
    now = datetime.now(timezone.utc)
    highlights = []
    for h in result.highlights[:TOP_N]:
        srcs = [items[n] for n in h.sources if 0 <= n < len(items)][:3]
        valid = news["taxonomy"].get(h.country, {}).get("visas", {})
        highlights.append({
            "headline": h.headline, "detail": h.detail, "impact": h.impact, "country": h.country,
            "visas": [v for v in h.visas if v in valid],
            "sources": [{"title": s["title"], "link": s["link"], "publisher": s["publisher"]} for s in srcs],
        })
    iso = now.isocalendar()
    out = {
        "week": f"{iso[0]}-W{iso[1]:02d}",
        "from": (now - timedelta(days=7)).date().isoformat(), "to": now.date().isoformat(),
        "generated": now.isoformat(), "model": MODEL, "item_count": len(items),
        "overview": result.overview, "highlights": highlights,
    }
    text = json.dumps(out, ensure_ascii=False, indent=1)
    (DATA / "summary.json").write_text(text, "utf-8")
    (DATA / "summaries").mkdir(exist_ok=True)
    (DATA / "summaries" / f'{out["week"]}.json').write_text(text, "utf-8")
    print(f"Đã tóm tắt {len(items)} tin -> {len(highlights)} điểm chính ({out['week']}).")


if __name__ == "__main__":
    main()

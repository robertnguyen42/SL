#!/usr/bin/env python3
"""Dùng Claude phân loại tin: có phải thay đổi chính sách không, và chính sách bị SIẾT hay được NỚI.
Kết quả lưu ở docs/data/ai_labels.json (theo id tin), rồi chấm lại điểm ưu tiên trong news.json.
Gom tin theo lô để tiết kiệm: chỉ gọi khi có >= MIN_BATCH tin chờ hoặc tin chờ lâu nhất đã quá MAX_WAIT.
Cần ANTHROPIC_API_KEY; thiếu thì bỏ qua (trang dùng nhãn theo từ khoá như cũ)."""
import json, os, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Literal

import fetch_news

ROOT = Path(__file__).parent
DATA = ROOT / "docs" / "data"
LABELS = DATA / "ai_labels.json"
MODEL = "claude-opus-5-5"
LOOKBACK_DAYS = 21       # chỉ phân loại tin trong 3 tuần gần nhất
MIN_BATCH = 40
MAX_WAIT = timedelta(hours=6)
BATCH_SIZE = 150

SYSTEM = """Bạn phân loại tiêu đề tin tức di trú cho đội tư vấn định cư người Việt.
Với mỗi tin, trả lời:
- policy: true nếu tin nói về một thay đổi (hoặc đề xuất thay đổi) chính sách, luật, quy định, phí, hạn mức,
  điều kiện, thời gian xử lý, lịch visa, kết quả rút hồ sơ, hay chương trình di trú của một quốc gia.
  false nếu là câu chuyện cá nhân, vụ án, quảng cáo, hướng dẫn chung, bình luận không kèm thay đổi cụ thể.
- direction: tác động lên KHẢ NĂNG DI TRÚ của người nước ngoài vào quốc gia đó:
  "siet" = khó hơn (tăng phí, giảm chỉ tiêu, tạm dừng, cấm, thêm điều kiện, trục xuất nhiều hơn, kéo dài một chính sách siết);
  "noi" = dễ hơn (giảm phí, tăng chỉ tiêu, diện mới, xử lý nhanh hơn, toà án chặn/hoãn một chính sách siết, lịch visa tiến lên);
  "khong_ro" = không rõ, trung tính, hoặc policy=false.
Đọc kỹ nghĩa cả câu: "toà án chặn phí H-1B 100.000 USD" là noi; "gia hạn phí H-1B 100.000 USD" là siet."""


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Chưa có ANTHROPIC_API_KEY, giữ nhãn theo từ khoá.")
        return
    force = os.environ.get("FORCE") == "1"
    now = datetime.now(timezone.utc)
    news = json.loads((DATA / "news.json").read_text("utf-8"))
    try:
        labels = json.loads(LABELS.read_text("utf-8"))
    except Exception:
        labels = {}

    pending = [i for i in news["items"] if i["id"] not in labels
               and now - datetime.fromisoformat(i["published"]) < timedelta(days=LOOKBACK_DAYS)]
    if not pending:
        print("Không có tin chờ phân loại.")
        return
    oldest = min(datetime.fromisoformat(i["fetched"]) for i in pending)
    if not force and len(pending) < MIN_BATCH and now - oldest < MAX_WAIT:
        print(f"{len(pending)} tin chờ, chưa đủ lô (>= {MIN_BATCH} tin hoặc chờ quá {MAX_WAIT}). Bỏ qua lần này.")
        return

    import anthropic
    from pydantic import BaseModel

    class Label(BaseModel):
        n: int
        policy: bool
        direction: Literal["siet", "noi", "khong_ro"]

    class Labels(BaseModel):
        labels: List[Label]

    client = anthropic.Anthropic()
    done = 0
    for start in range(0, len(pending), BATCH_SIZE):
        batch = pending[start:start + BATCH_SIZE]
        lines = "\n".join(f'[{n}] {i["country"]} | {i["title"]}' for n, i in enumerate(batch))
        try:
            resp = client.messages.parse(
                model=MODEL,
                max_tokens=16000,
                output_config={"effort": "low"},
                system=SYSTEM,
                messages=[{"role": "user", "content": f"Phân loại {len(batch)} tin sau, trả về đúng một nhãn cho mỗi số [n]:\n\n{lines}"}],
                output_format=Labels,
            )
        except anthropic.APIError as e:
            print(f"Lỗi gọi Claude ({type(e).__name__}): {e}. Giữ nhãn từ khoá cho lô này.", file=sys.stderr)
            continue
        if resp.stop_reason == "refusal" or resp.parsed_output is None:
            print(f"Claude không trả kết quả (stop_reason={resp.stop_reason}), bỏ qua lô này.", file=sys.stderr)
            continue
        for lb in resp.parsed_output.labels:
            if 0 <= lb.n < len(batch):
                labels[batch[lb.n]["id"]] = {"p": lb.policy, "d": None if lb.direction == "khong_ro" else lb.direction}
                done += 1
        print(f"Lô {start // BATCH_SIZE + 1}: {len(batch)} tin, {resp.usage.input_tokens} in / {resp.usage.output_tokens} out tokens")

    # Bỏ nhãn của tin đã bị xoá khỏi news.json để file không phình mãi
    ids = {i["id"] for i in news["items"]}
    labels = {k: v for k, v in labels.items() if k in ids}
    LABELS.write_text(json.dumps(labels, ensure_ascii=False, separators=(",", ":")), "utf-8")

    # Chấm lại điểm với nhãn AI để trang web dùng ngay, không cần chờ lần lấy tin sau
    tax, pr = fetch_news.load_taxonomy(), fetch_news.load_priority()
    news["items"] = [fetch_news.score(i, tax, pr, labels) for i in news["items"]]
    (DATA / "news.json").write_text(json.dumps(news, ensure_ascii=False, indent=1), "utf-8")
    print(f"Đã phân loại {done}/{len(pending)} tin.")


if __name__ == "__main__":
    main()

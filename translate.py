#!/usr/bin/env python3
"""Dịch tiêu đề (và tóm tắt nếu có) của tin tiếng Anh sang tiếng Việt bằng Claude.
Kết quả lưu ở docs/data/translations.json theo id tin: {id: {"t": tiêu đề, "s": tóm tắt}}.
fetch_news.py đọc file này và gắn title_vi / summary_vi vào từng tin; trang web hiện bản tiếng Việt,
bản gốc tiếng Anh vẫn giữ để đối chiếu.
Mỗi tin chỉ dịch một lần. Cần ANTHROPIC_API_KEY; thiếu thì bỏ qua, trang hiện tiêu đề gốc như cũ.

Biến môi trường:
  TRANSLATE_MODEL   model Claude dùng để dịch (mặc định MODEL bên dưới)
  TRANSLATE_DAYS    chỉ dịch tin trong N ngày gần nhất (mặc định 120 = toàn bộ tin đang giữ)
  TRANSLATE_LIMIT   tối đa bao nhiêu tin mỗi lần chạy (mặc định 600), để chi phí mỗi lần có giới hạn
  TRANSLATE_SINCE   chỉ dịch tin lấy về từ thời điểm này trở đi (ISO, vd 2026-11-09T00:00:00+00:00);
                    dùng để không dịch bù tin cũ"""
import json, os, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Literal

import fetch_news

ROOT = Path(__file__).parent
DATA = ROOT / "docs" / "data"
OUT = DATA / "translations.json"
MODEL = os.environ.get("TRANSLATE_MODEL") or "claude-opus-5-5"
DAYS = int(os.environ.get("TRANSLATE_DAYS") or 120)
LIMIT = int(os.environ.get("TRANSLATE_LIMIT") or 600)
SINCE = os.environ.get("TRANSLATE_SINCE") or ""
BATCH_SIZE = 60

SYSTEM = """Bạn dịch tin tức di trú sang tiếng Việt cho đội tư vấn định cư người Việt (đọc nội bộ, văn phong báo chí, trang trọng).
Quy tắc:
- Dịch đúng nghĩa, ngắn gọn như tiêu đề báo tiếng Việt. Không thêm, bớt hay bình luận thông tin.
- GIỮ NGUYÊN tiếng Anh các thuật ngữ chuyên ngành, tên chương trình, tên cơ quan viết tắt và số hiệu visa:
  ví dụ visa 482, subclass 491, EB-5, H-1B, F-1, OPT, Green Card, Visa Bulletin, Express Entry, PNP, CRS, LMIA,
  Golden Visa, Freezone, FIRB, USCIS, IRCC, DHS, INZ, Home Affairs, Skilled Migrant, Active Investor Plus, AEWV, ETIAS, EES.
- Tên người, tên tổ chức, tên địa danh giữ nguyên hoặc dùng tên tiếng Việt thông dụng (Mỹ, Úc, Canada, New Zealand, Anh, Dubai).
- Số tiền giữ đơn vị gốc (USD, AUD, CAD, NZD, EUR, AED); ngày viết dạng ngày/tháng/năm.
- Bỏ phần " - Tên báo" ở cuối tiêu đề nếu có.
- Nếu có tóm tắt thì dịch tóm tắt; không có thì để chuỗi rỗng.
Đồng thời phân loại mỗi tin:
- policy: true nếu tin nói về một thay đổi (hoặc đề xuất thay đổi) chính sách, luật, quy định, phí, hạn mức, mức đầu tư,
  điều kiện, thời gian xử lý, lịch visa, kế hoạch nhập cư hay chương trình di trú của một quốc gia; kể cả phân tích của
  luật sư / chuyên gia về một thay đổi cụ thể. false nếu là quảng cáo dự án, hội thảo, câu chuyện cá nhân, hướng dẫn chung.
- direction: tác động lên khả năng di trú của người nước ngoài: "siet" (khó hơn), "noi" (dễ hơn), "khong_ro"."""


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Chưa có ANTHROPIC_API_KEY, bỏ qua bước dịch.")
        return
    now = datetime.now(timezone.utc)
    news = json.loads((DATA / "news.json").read_text("utf-8"))
    try:
        done = json.loads(OUT.read_text("utf-8"))
    except Exception:
        done = {}

    # Tin mới nhất, tin chính phủ và tin chính sách dịch trước
    # Chỉ dịch tin thuộc chương trình SI (programs.json) để không tốn phí cho tin ngoài phạm vi
    pending = [i for i in news["items"] if i.get("lang") != "vi" and i["id"] not in done and i.get("si")
               and now - datetime.fromisoformat(i["published"]) < timedelta(days=DAYS)
               and (not SINCE or datetime.fromisoformat(i["fetched"]) >= datetime.fromisoformat(SINCE))]
    pending.sort(key=lambda i: (i["published"][:10], i.get("score", 0)), reverse=True)
    pending = pending[:LIMIT]
    if not pending:
        print("Không có tin chờ dịch.")
        return

    import anthropic
    from pydantic import BaseModel

    class Item(BaseModel):
        n: int
        title: str
        summary: str
        policy: bool
        direction: Literal["siet", "noi", "khong_ro"]

    class Batch(BaseModel):
        items: List[Item]

    labels_path = DATA / "ai_labels.json"
    try:
        labels = json.loads(labels_path.read_text("utf-8"))
    except Exception:
        labels = {}
    client = anthropic.Anthropic()
    ok = tin = tout = 0
    for start in range(0, len(pending), BATCH_SIZE):
        batch = pending[start:start + BATCH_SIZE]
        lines = "\n".join(f'[{n}] TIÊU ĐỀ: {i["title"]}' + (f'\n    TÓM TẮT: {i["summary"]}' if i.get("summary") else "")
                          for n, i in enumerate(batch))
        try:
            resp = client.messages.parse(
                model=MODEL,
                max_tokens=16000,
                output_config={"effort": "low"},
                system=SYSTEM,
                messages=[{"role": "user", "content": f"Dịch {len(batch)} tin sau, trả về đúng một kết quả cho mỗi số [n]:\n\n{lines}"}],
                output_format=Batch,
            )
        except anthropic.APIError as e:
            print(f"Lỗi gọi Claude ({type(e).__name__}): {e}. Bỏ qua lô này, lần sau dịch lại.", file=sys.stderr)
            continue
        if resp.stop_reason == "refusal" or resp.parsed_output is None:
            print(f"Claude không trả kết quả (stop_reason={resp.stop_reason}), bỏ qua lô này.", file=sys.stderr)
            continue
        for it in resp.parsed_output.items:
            if 0 <= it.n < len(batch) and it.title.strip():
                done[batch[it.n]["id"]] = {"t": it.title.strip(), **({"s": it.summary.strip()} if it.summary.strip() else {})}
                # Nhãn chính sách / siết-nới do Claude đánh giá, thay cho nhãn theo từ khoá (fetch_news đọc ai_labels.json)
                labels[batch[it.n]["id"]] = {"p": it.policy, "d": None if it.direction == "khong_ro" else it.direction}
                ok += 1
        tin += resp.usage.input_tokens
        tout += resp.usage.output_tokens
        print(f"Lô {start // BATCH_SIZE + 1}: {len(batch)} tin, {resp.usage.input_tokens} in / {resp.usage.output_tokens} out tokens")

    # Bỏ bản dịch của tin đã bị xoá khỏi news.json để file không phình mãi
    ids = {i["id"] for i in news["items"]}
    done = {k: v for k, v in done.items() if k in ids}
    OUT.write_text(json.dumps(done, ensure_ascii=False, separators=(",", ":")), "utf-8")
    labels_path.write_text(json.dumps({k: v for k, v in labels.items() if k in ids}, ensure_ascii=False, separators=(",", ":")), "utf-8")

    # Gắn bản dịch vào news.json ngay để trang web dùng, không cần chờ lần lấy tin sau
    tiers = fetch_news.load_tiers()
    for i in news["items"]:
        t = done.get(i["id"])
        if t and i.get("lang") != "vi":
            i["title_vi"] = t["t"]
            if t.get("s"):
                i["summary_vi"] = t["s"]
        lb = labels.get(i["id"])
        if lb:
            i["policy"], i["direction"], i["ai"] = lb["p"] or i["type"] == "official", lb["d"], True
        i.setdefault("tier", fetch_news.source_tier(i, tiers))
    (DATA / "news.json").write_text(json.dumps(news, ensure_ascii=False, indent=1), "utf-8")
    print(f"Đã dịch {ok}/{len(pending)} tin bằng {MODEL}; {tin} in / {tout} out tokens. "
          f"Còn {sum(1 for i in news['items'] if i.get('lang') != 'vi' and i['id'] not in done)} tin tiếng Anh chưa dịch.")


if __name__ == "__main__":
    main()

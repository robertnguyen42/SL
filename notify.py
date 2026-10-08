#!/usr/bin/env python3
"""Gửi email bản tin di trú định kỳ (mặc định 3 ngày/lần) cho nhóm nội bộ.
Đọc docs/data/news.json, lấy tin mới kể từ lần gửi trước, nhóm theo Nước -> Loại visa.

Cấu hình qua biến môi trường (GitHub secrets, không ghi vào code vì repo công khai):
  SMTP_USER  email gửi đi (vd. tài khoản Google Workspace)
  SMTP_PASS  mật khẩu ứng dụng (App Password) của tài khoản đó
  EMAIL_TO   danh sách người nhận, cách nhau bằng dấu phẩy
  SMTP_HOST  mặc định smtp.gmail.com (cổng 465, SSL)
Chạy thử không gửi:  python3 notify.py --preview preview.html
Gửi ngay, bỏ qua lịch: FORCE=1 python3 notify.py"""
import json, os, sys, html, smtplib, ssl
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "docs" / "data"
STATE = DATA / "notify_state.json"
SITE = "https://robertnguyen42.github.io/SL/"
INTERVAL_DAYS = 3
COUNTRIES = ["US", "AU", "EU"]   # thứ tự hiển thị trong email; thêm "CA", "NZ" khi cần
MAX_PER_COUNTRY = 15     # tối đa số tin hiển thị mỗi nước
PER_GROUP = 3            # tối đa số tin mỗi diện visa
VN = timezone(timedelta(hours=7))


def load_state():
    try:
        return json.loads(STATE.read_text("utf-8"))
    except Exception:
        return {}


def pick_items(news, since):
    """Tin mới kể từ `since`, ưu tiên nguồn chính phủ rồi đến tin có nhãn visa."""
    out = {}
    for c in COUNTRIES:
        items = [i for i in news["items"] if i["country"] == c
                 and datetime.fromisoformat(i["fetched"]) > since
                 and datetime.fromisoformat(i["published"]) > since - timedelta(days=2)]
        # news.json đã xếp mới nhất trước; sort ổn định nên giữ thứ tự đó trong từng nhóm
        items.sort(key=lambda i: (i["type"] != "official", not i.get("visas")))
        out[c] = items
    return out


def build_html(groups, tax, since, now, summary):
    esc = html.escape
    total = sum(len(v) for v in groups.values())
    rng = f"{since.astimezone(VN):%d/%m} – {now.astimezone(VN):%d/%m/%Y}"
    parts = [f"""<div style="font-family:Arial,Helvetica,sans-serif;max-width:680px;margin:0 auto;color:#1a1d23;font-size:14px;line-height:1.5">
<h1 style="font-size:20px;margin:0 0 4px">Bản tin Di trú</h1>
<p style="margin:0 0 16px;color:#667085">{rng} · {total} tin mới · <a href="{SITE}" style="color:#1d4ed8">Mở trang web</a></p>"""]
    if summary:
        parts.append('<div style="background:#eef2ff;border-radius:8px;padding:12px 14px;margin-bottom:18px">'
                     '<b>Tóm tắt tuần (AI)</b><ol style="margin:6px 0 0;padding-left:20px">')
        for h in summary["highlights"]:
            parts.append(f'<li style="margin-bottom:4px"><b>{esc(h["headline"])}</b> – {esc(h["detail"])}</li>')
        parts.append("</ol></div>")
    for c, items in groups.items():
        t = tax.get(c, {})
        parts.append(f'<h2 style="font-size:17px;margin:22px 0 6px;border-bottom:2px solid #e4e7ec;padding-bottom:4px">'
                     f'{t.get("flag", "")} {esc(t.get("name", c))} <span style="color:#667085;font-weight:normal;font-size:13px">· {len(items)} tin</span></h2>')
        if not items:
            parts.append('<p style="color:#667085;margin:4px 0">Không có tin mới.</p>')
            continue
        # Nhóm theo diện visa chính, mỗi nhóm tối đa PER_GROUP tin để một sự kiện không chiếm hết email
        by_visa = {}
        for i in items:
            by_visa.setdefault((i.get("visas") or ["_other"])[0], []).append(i)
        order = sorted(by_visa, key=lambda v: (v == "_other", -len(by_visa[v])))
        shown = 0
        for v in order:
            if shown >= MAX_PER_COUNTRY:
                break
            group = by_visa[v]
            label = "Tin chung" if v == "_other" else t.get("visas", {}).get(v, v)
            parts.append(f'<h3 style="font-size:14px;margin:14px 0 4px;color:#1d4ed8">{esc(label)} '
                         f'<span style="color:#667085;font-weight:normal">({len(group)})</span></h3>')
            for i in group[:PER_GROUP]:
                date = datetime.fromisoformat(i["published"]).astimezone(VN)
                gov = ('<span style="background:#1d4ed8;color:#fff;border-radius:3px;padding:0 5px;font-size:11px">CHÍNH PHỦ</span> '
                       if i["type"] == "official" else "")
                parts.append(f'<div style="margin:4px 0 8px"><a href="{esc(i["link"])}" style="color:#1a1d23;text-decoration:none">{esc(i["title"])}</a>'
                             f'<div style="font-size:12px;color:#667085">{gov}{esc(i["publisher"])} · {date:%d/%m %H:%M}</div></div>')
                shown += 1
            if len(group) > PER_GROUP:
                parts.append(f'<div style="font-size:12px;margin:-2px 0 6px"><a href="{SITE}" style="color:#667085">+ {len(group) - PER_GROUP} tin cùng chủ đề trên web</a></div>')
    parts.append('<p style="margin-top:28px;font-size:12px;color:#98a2b3">Email nội bộ, gửi tự động 3 ngày/lần. '
                 'Tin tổng hợp từ báo chí và nguồn chính phủ, chỉ để tham khảo, không thay thế tư vấn pháp lý.</p></div>')
    return "".join(parts), total, rng


def build_text(groups, tax, rng):
    lines = [f"Bản tin Di trú {rng}", SITE, ""]
    for c, items in groups.items():
        lines.append(f"== {tax.get(c, {}).get('name', c)} ({len(items)} tin)")
        lines += [f"- {i['title']}\n  {i['link']}" for i in items[:MAX_PER_COUNTRY]]
        lines.append("")
    return "\n".join(lines)


def main():
    preview = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--preview" else None
    now = datetime.now(timezone.utc)
    state = load_state()
    last = datetime.fromisoformat(state["last_sent"]) if state.get("last_sent") else now - timedelta(days=INTERVAL_DAYS)

    if not preview and not os.environ.get("FORCE") and now - last < timedelta(days=INTERVAL_DAYS, hours=-2):
        print(f"Lần gửi trước {last:%d/%m %H:%M} UTC, chưa đủ {INTERVAL_DAYS} ngày. Bỏ qua.")
        return
    if not preview and not all(os.environ.get(k) for k in ("SMTP_USER", "SMTP_PASS", "EMAIL_TO")):
        print("Chưa cấu hình SMTP_USER / SMTP_PASS / EMAIL_TO, bỏ qua gửi email.")
        return

    news = json.loads((DATA / "news.json").read_text("utf-8"))
    summary = None
    try:
        s = json.loads((DATA / "summary.json").read_text("utf-8"))
        if now - datetime.fromisoformat(s["generated"]) < timedelta(days=INTERVAL_DAYS):
            summary = s
    except Exception:
        pass

    groups = pick_items(news, last)
    body, total, rng = build_html(groups, news["taxonomy"], last, now, summary)
    if preview:
        Path(preview).write_text(body, "utf-8")
        print(f"Đã ghi bản xem trước: {preview} ({total} tin)")
        return
    if total == 0:
        print("Không có tin mới, không gửi.")
        return

    names = {c: news["taxonomy"][c]["name"] for c in COUNTRIES}
    counts = " · ".join(f"{names[c]} {len(groups[c])}" for c in COUNTRIES if groups[c])
    to = [e.strip() for e in os.environ["EMAIL_TO"].split(",") if e.strip()]
    msg = EmailMessage()
    msg["Subject"] = f"Bản tin Di trú {rng}: {total} tin mới ({counts})"
    msg["From"] = formataddr(("Bản tin Di trú", os.environ["SMTP_USER"]))
    msg["To"] = ", ".join(to)
    msg.set_content(build_text(groups, news["taxonomy"], rng))
    msg.add_alternative(body, subtype="html")

    host = os.environ.get("SMTP_HOST") or "smtp.gmail.com"
    with smtplib.SMTP_SSL(host, 465, context=ssl.create_default_context()) as s:
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        s.send_message(msg)
    STATE.write_text(json.dumps({"last_sent": now.isoformat(), "count": total}, indent=1), "utf-8")
    print(f"Đã gửi {total} tin tới {len(to)} người nhận.")


if __name__ == "__main__":
    main()

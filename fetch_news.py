#!/usr/bin/env python3
"""Lấy tin di trú -> docs/data/news.json, gắn nhãn Nước -> Loại visa theo keywords.json.
Nguồn = sources.json (cố định) + Google News tự sinh từ trường 'q' trong keywords.json.
Chỉ dùng thư viện chuẩn của Python, không cần cài thêm gì."""
import json, hashlib, re, html, sys, time
import urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "docs" / "data" / "news.json"
KEEP_DAYS = 120          # giữ tin trong 120 ngày
MAX_PER_SOURCE = 40
ATOM = "{http://www.w3.org/2005/Atom}"
# Tin báo chí (type=news) phải chứa ít nhất 1 từ khoá chung này hoặc 1 từ khoá visa, để loại tin không liên quan
GENERAL = re.compile(r"visa|thị thực|định cư|di trú|nhập cư|nhập tịch|thường trú|quốc tịch|du học|"
                     r"immigra|migra|citizenship|residen|uscis|ircc|home affairs|green card|thẻ xanh|"
                     r"asylum|refugee|tị nạn|border|deport|trục xuất", re.I)
# Loại hẳn tin chứa các cụm này (nhiễu phổ biến)
EXCLUDE = re.compile(r"tái định cư|giải phóng mặt bằng|khu tái định|hoa hậu|showbiz", re.I)
NUM_PREFIX = r"(?:visa|subclass|diện|thị thực|loại)"


def kw_pattern(k):
    """Số thuần (482) chỉ khớp khi có 'visa/subclass/diện' đi kèm; chữ viết hoa (TSS, US) khớp đúng hoa thường."""
    if k.isdigit():
        return rf"(?:{NUM_PREFIX}\s*(?:\d+\s*/\s*)*#?{k}\b|\b{k}\s*(?:/\s*\d+\s*)*visa)", re.I
    flags = 0 if (k.isupper() and len(k) <= 5) else re.I
    return rf"(?<!\w){re.escape(k)}", flags


def compile_kws(words):
    pats = [kw_pattern(k) for k in words]
    ci = [p for p, f in pats if f]
    cs = [p for p, f in pats if not f]
    return [re.compile("|".join(ci), re.I)] * bool(ci) + [re.compile("|".join(cs))] * bool(cs)


def matches(regs, text):
    return any(r.search(text) for r in regs)


def load_taxonomy():
    raw = json.loads((ROOT / "keywords.json").read_text("utf-8"))
    tax = {}
    for c, v in raw.items():
        if c.startswith("_"):
            continue
        tax[c] = {"name": v["name"], "flag": v["flag"], "re": compile_kws(v["country"]),
                  "visas": {vid: {"name": x["name"], "q": x.get("q", ""), "re": compile_kws(x["kw"])}
                            for vid, x in v["visas"].items()}}
    return tax


def tag(item, tax):
    """Gán lại nước (nếu tiêu đề nói rõ nước khác) và danh sách loại visa."""
    text = item["title"] + " " + item.get("summary", "")
    hit = [c for c, t in tax.items() if matches(t["re"], text)]
    if item["country"] not in hit and len(hit) == 1:
        item["country"] = hit[0]
    t = tax.get(item["country"])
    item["visas"] = [vid for vid, v in t["visas"].items() if matches(v["re"], text)] if t else []
    return item


def all_sources(tax):
    srcs = json.loads((ROOT / "sources.json").read_text("utf-8"))
    for c, t in tax.items():
        for vid, v in t["visas"].items():
            if v["q"]:
                q = urllib.parse.quote(v["q"] + " when:30d")
                srcs.append({"id": f"{c.lower()}-{vid}", "country": c, "type": "news", "visa": vid,
                             "name": f"Google News – {t['name']} – {v['name']}",
                             "url": f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"})
    return srcs


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (DiTruNewsBot)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def clean(text, limit=300):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def parse_feed(raw):
    root = ET.fromstring(raw)
    items = []
    for it in root.iter("item"):  # RSS
        src = it.find("source")
        items.append({
            "title": it.findtext("title", ""),
            "link": it.findtext("link", ""),
            "date": it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date"),
            "summary": it.findtext("description", ""),
            "publisher": src.text if src is not None else None,
        })
    for e in root.iter(ATOM + "entry"):  # Atom
        link = e.find(ATOM + "link")
        items.append({
            "title": e.findtext(ATOM + "title", ""),
            "link": link.get("href") if link is not None else "",
            "date": e.findtext(ATOM + "published") or e.findtext(ATOM + "updated"),
            "summary": e.findtext(ATOM + "summary") or e.findtext(ATOM + "content") or "",
            "publisher": None,
        })
    return items


def norm_title(t):
    # Google News thêm " - Tên báo" ở cuối tiêu đề; bỏ đi để chống trùng
    return re.sub(r"\s+-\s+[^-]{2,60}$", "", t).strip().lower()


def main():
    tax = load_taxonomy()
    sources = all_sources(tax)
    old = json.loads(OUT.read_text("utf-8")) if OUT.exists() else {"items": []}
    by_id = {i["id"]: i for i in old.get("items", [])}
    seen_titles = {norm_title(i["title"]) for i in by_id.values()}
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=KEEP_DAYS)
    status, added = [], 0

    for s in sources:
        try:
            entries = parse_feed(fetch(s["url"]))[:MAX_PER_SOURCE]
            status.append({"id": s["id"], "name": s["name"], "ok": True, "count": len(entries)})
        except Exception as ex:
            status.append({"id": s["id"], "name": s["name"], "ok": False, "error": str(ex)[:200]})
            print(f"[LỖI] {s['name']}: {ex}", file=sys.stderr)
            continue
        finally:
            time.sleep(0.5)  # nhẹ tay với Google News
        for e in entries:
            title = clean(e["title"], 400)
            if not title or not e["link"]:
                continue
            visa_re = tax[s["country"]]["visas"][s["visa"]]["re"] if s.get("visa") else []
            if s["type"] == "news" and not (GENERAL.search(title) or matches(visa_re, title)):
                continue
            d = parse_date(e["date"]) or now
            if d < cutoff:
                continue
            iid = hashlib.sha1(e["link"].encode()).hexdigest()[:16]
            nt = norm_title(title)
            if iid in by_id or nt in seen_titles:
                continue
            seen_titles.add(nt)
            by_id[iid] = {
                "id": iid,
                "title": title,
                "link": e["link"].strip(),
                "summary": "" if s["type"] == "news" else clean(e["summary"]),
                "publisher": e["publisher"] or s["name"],
                "country": s["country"],
                "type": s["type"],
                "source": s["id"],
                "published": d.isoformat(),
                "fetched": now.isoformat(),
            }
            added += 1

    # Gắn nhãn lại toàn bộ, để sửa keywords.json là áp dụng ngay cho cả tin cũ
    items = [tag(i, tax) for i in by_id.values()
             if parse_date(i["published"]) >= cutoff and not EXCLUDE.search(i["title"])]
    items.sort(key=lambda i: i["published"], reverse=True)
    taxonomy = {c: {"name": t["name"], "flag": t["flag"],
                    "visas": {vid: v["name"] for vid, v in t["visas"].items()}} for c, t in tax.items()}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"updated": now.isoformat(), "taxonomy": taxonomy, "sources": status,
                               "items": items}, ensure_ascii=False, indent=1), "utf-8")
    print(f"Thêm {added} tin mới, tổng {len(items)} tin, {sum(1 for i in items if i['visas'])} tin có nhãn visa.")


if __name__ == "__main__":
    main()

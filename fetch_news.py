#!/usr/bin/env python3
"""Lấy tin di trú -> docs/data/news.json, gắn nhãn Nước -> Loại visa theo keywords.json.
Nguồn = sources.json (cố định) + Google News tự sinh từ trường 'q' trong keywords.json.
Chỉ dùng thư viện chuẩn của Python, không cần cài thêm gì."""
import csv, io, json, hashlib, re, html, sys, time
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
EXCLUDE = re.compile(r"tái định cư|giải phóng mặt bằng|khu tái định|hoa hậu|showbiz|Centene|prior authorization|Philippine|Visayas|Mindanao|Luzon|Cebu|PNP chief", re.I)  # PNP = cảnh sát Philippines
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


# ---------- Keyword từ Google Sheet (sync_keywords.py tải về sheet_keywords.csv) ----------
SHEET = ROOT / "sheet_keywords.csv"
SHEET_COUNTRY = {"ÚC": "AU", "UC": "AU", "NEW ZEALAND": "NZ", "MỸ": "US", "MY": "US", "CANADA": "CA",
                 "CHÂU ÂU": "EU", "CHAU AU": "EU", "DUBAI": "AE", "UAE": "AE"}
SHEET_GROUP = {"chung các loại": "chung", "tay nghề": "tay-nghe", "đầu tư": "dau-tu", "khác": "khac"}
GROUP_NAMES = {"chung": "Chung các loại", "tay-nghe": "Tay nghề", "dau-tu": "Đầu tư", "khac": "Khác"}
PRIO_GROUPS = {"tay-nghe", "dau-tu"}               # nhóm định cư lâu dài, xếp lên trên
QUERY_CTX = {"AU": "Australia", "NZ": '"New Zealand"', "CA": "Canada", "AE": "(UAE OR Dubai)", "US": "", "EU": ""}
STOP_TERMS = {"job", "regional", "sbs", "sponsor", "nomination"}   # quá chung chung (SBS trùng tên đài; sponsor/nomination trùng tài trợ, đề cử giải thưởng)
TYPO = {"UB-3 Skilled": "EB-3 Skilled", "Skill Migration Category": "Skilled Migrant Category",
        "regional center": "EB-5 regional center"}   # "regional center" đứng một mình trùng trung tâm cộng đồng ở Mỹ
MONTHS = r"(January|February|March|April|May|June|July|August|September|October|November|December)"


def split_cell(cell):
    """Tách ô keyword theo dấu phẩy/xuống dòng, bỏ qua dấu phẩy nằm trong ngoặc."""
    out, buf, depth = [], "", 0
    for n, ch in enumerate(cell):
        depth += ch == "("
        depth -= ch == ")"
        in_number = ch == "," and n + 1 < len(cell) and cell[n - 1:n].isdigit() and cell[n + 1].isdigit()  # 250,000
        if ch in ",\n" and depth == 0 and not in_number:
            out.append(buf); buf = ""
        else:
            buf += ch
    out.append(buf)
    return [x.strip() for x in out if x.strip()]


def expand(phrase):
    """Một keyword trong sheet -> (các cụm để khớp tiêu đề, cụm để tìm Google News)."""
    for a, b in TYPO.items():
        phrase = phrase.replace(a, b)
    stripped = re.sub(r"(AED|€|\$)\s?[\d.,]+(\s?(million|m)\b)?(/(AED|€|\$)?\s?[\d.,]+)*", "", phrase).strip(" ,")
    if stripped != phrase and len(stripped.split()) < 3:
        return [], []        # "Gold Card $1 million" -> "Gold Card" quá chung (trùng thẻ bảo hiểm...), bỏ
    phrase = stripped
    main, paren = phrase, ""
    m = re.match(r"^(.*?)\s*\((.*)\)\s*$", phrase)
    if m:
        main, paren = m.group(1).strip(), m.group(2).strip()
    terms, numeric = [], False
    for part in [main, paren]:
        if not part:
            continue
        pieces = part.split("/")
        nums = [p for p in pieces if re.fullmatch(r"\d{3}", p.strip().split()[-1] if p.strip() else "")]
        if len(pieces) > 1 and len(nums) == len(pieces):           # subclass 482/186/... hoặc 600/500/...
            prefix = " ".join(pieces[0].split()[:-1])
            for p in pieces:                                         # "subclass 482" và "482" (cần chữ visa đi kèm)
                num = p.strip().split()[-1]
                terms += [f"{prefix} {num}".strip(), num]
            numeric = True
        elif len(pieces) > 1 and re.fullmatch(r"[A-Z0-9-]{2,6}", pieces[0].strip()):   # OPT/STEM OPT
            terms += [p.strip() for p in pieces]
        else:
            terms.append(part)
            words = part.split()
            if len(words) >= 4:                                     # cụm dài: thêm phần lõi 2-3 từ đầu
                core = words[:3]
                while core and re.fullmatch(rf"\d[\d–-]*|{MONTHS}|on|for|of|to|vs|after|the|and|in", core[-1], re.I):
                    core.pop()
                if len(core) >= 2:
                    terms.append(" ".join(core))
    terms = [t for t in dict.fromkeys(terms) if t.lower() not in STOP_TERMS]
    query = paren if len(paren) > len(main) and not re.fullmatch(r"[\d/ ]+", main) else main
    if re.fullmatch(r"[\d/ ]+", main) or numeric:
        query = ""                                                  # số thuần: dùng từng số bên dưới
    if query.lower() in STOP_TERMS:
        query = ""
    queries = [query] if query else []
    queries += [f"{t.split()[-1]} visa" for t in terms if re.fullmatch(r"(subclass )?\d{3}", t)]
    return terms, queries


def compile_terms(terms):
    """Khớp nguyên cụm (eTA không khớp 'beta'); số thuần (482) vẫn cần chữ visa/subclass đi kèm."""
    ci, cs = [], []
    for t in terms:
        if t.isdigit():
            ci.append(kw_pattern(t)[0])
        elif t.isupper() and len(t) <= 5:
            cs.append(rf"(?<!\w){re.escape(t)}(?!\w)")
        else:
            ci.append(rf"(?<!\w){re.escape(t)}(?!\w)")
    return [re.compile("|".join(ci), re.I)] * bool(ci) + [re.compile("|".join(cs))] * bool(cs)


def load_sheet():
    """{nước: {nhóm: {"terms": [...], "queries": [...]}}} từ sheet_keywords.csv."""
    out = {}
    if not SHEET.exists():
        return out
    country = None
    for row in csv.reader(io.StringIO(SHEET.read_text("utf-8"))):
        row = (row + ["", "", "", ""])[:4]
        name, group, cell = row[1].strip(), row[2].strip(), row[3]
        if name.upper() == "QUỐC GIA":
            continue
        if name:
            country = SHEET_COUNTRY.get(name.upper())
        gid = SHEET_GROUP.get(group.lower())
        if not country or not gid or not cell.strip():
            continue
        g = out.setdefault(country, {}).setdefault(gid, {"terms": [], "queries": []})
        for ph in split_cell(cell):
            t, q = expand(ph)
            g["terms"] += t
            g["queries"] += q
    return out


def load_taxonomy():
    raw = json.loads((ROOT / "keywords.json").read_text("utf-8"))
    tax = {}
    for c, v in raw.items():
        if c.startswith("_"):
            continue
        tax[c] = {"name": v["name"], "flag": v["flag"], "re": compile_kws(v["country"]),
                  "visas": {vid: {"name": x["name"], "q": x.get("q", ""), "re": compile_kws(x["kw"]),
                                  "prio": bool(x.get("uu_tien")), "group": x.get("nhom")}
                            for vid, x in v["visas"].items()}}
    for c, groups in load_sheet().items():
        if c not in tax:
            continue
        tax[c]["groups"] = {gid: {"name": GROUP_NAMES[gid], "re": compile_terms(g["terms"]), "queries": g["queries"],
                                  "prio": gid in PRIO_GROUPS}
                            for gid, g in groups.items() if g["terms"]}
    return tax


VI_CHARS = re.compile(r"[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]", re.I)


def load_priority():
    raw = json.loads((ROOT / "keywords.json").read_text("utf-8")).get("_uu_tien", {})
    def words(ws):  # khớp nguyên từ; "abc*" = khớp tiền tố
        pats = [rf"(?<!\w){re.escape(w[:-1])}" if w.endswith("*") else rf"(?<!\w){re.escape(w)}(?!\w)" for w in ws]
        return [re.compile("|".join(pats), re.I)] if pats else []
    return {k: words(raw.get(k, [])) for k in ("chinh_sach", "siet", "noi")}


def tag(item, tax):
    """Gán lại nước (nếu tiêu đề nói rõ nước khác) và danh sách loại visa."""
    text = item["title"] + " " + item.get("summary", "")
    hit = [c for c, t in tax.items() if matches(t["re"], text)]
    if item["country"] not in hit and len(hit) == 1:
        item["country"] = hit[0]
    t = tax.get(item["country"])
    item["visas"] = [vid for vid, v in t["visas"].items() if matches(v["re"], text)] if t else []
    groups = (t or {}).get("groups", {})
    from_visa = {t["visas"][v]["group"] for v in item["visas"]} if t else set()
    item["groups"] = [gid for gid, g in groups.items() if gid in from_visa or matches(g["re"], text)
                      or (item.get("src_group") == gid and item.get("src_country") == item["country"]
                          and GENERAL.search(item["title"]))]   # tin từ truy vấn sheet phải có từ khoá di trú
    return item


def score(item, tax, pr, ai=None):
    """Ưu tiên: tiếng Việt, tin thay đổi chính sách (kèm hướng siết/nới), diện visa định cư chính.
    `ai`: nhãn Claude từ classify.py ({id: {"p": bool, "d": "siet"|"noi"|None}}); có thì dùng thay cho từ khoá."""
    title = item["title"]
    item["lang"] = "vi" if len(VI_CHARS.findall(title)) >= 3 else "en"
    label = (ai or {}).get(item["id"])
    if label:
        item["policy"], item["direction"], item["ai"] = label["p"] or item["type"] == "official", label["d"], True
    else:
        tighten, ease = matches(pr["siet"], title), matches(pr["noi"], title)
        item["policy"] = item["type"] == "official" or tighten or ease or matches(pr["chinh_sach"], title)
        item["direction"] = "siet" if tighten and not ease else "noi" if ease and not tighten else None
        item.pop("ai", None)
    visas = tax.get(item["country"], {}).get("visas", {})
    groups = tax.get(item["country"], {}).get("groups", {})
    item["prio"] = (any(visas[v]["prio"] for v in item.get("visas", []) if v in visas)
                    or any(groups[g]["prio"] for g in item.get("groups", []) if g in groups))
    item["score"] = (2 * (item["lang"] == "vi") + 2.5 * item["policy"] + 1.5 * item["prio"]
                     + 1 * (item["type"] == "official"))
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
        # Keyword trong Google Sheet: gom 6 cụm/lần tìm để không gọi Google News quá nhiều
        for gid, g in t.get("groups", {}).items():
            qs = list(dict.fromkeys(g["queries"]))
            for n in range(0, len(qs), 6):
                ors = " OR ".join(f'"{x}"' for x in qs[n:n + 6])
                q = urllib.parse.quote(f'{QUERY_CTX.get(c, "")} ({ors}) when:14d'.strip())
                srcs.append({"id": f"{c.lower()}-sheet-{gid}-{n // 6 + 1}", "country": c, "type": "news", "group": gid,
                             "name": f"Sheet – {t['name']} – {GROUP_NAMES[gid]} ({n // 6 + 1})",
                             "url": f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"})
                # Bing News: cùng truy vấn (7 ngày gần nhất), có đoạn tóm tắt bài mà Google News không có
                bq = urllib.parse.quote(f'{QUERY_CTX.get(c, "")} {ors}'.strip())
                srcs.append({"id": f"{c.lower()}-bing-{gid}-{n // 6 + 1}", "country": c, "type": "news", "group": gid,
                             "name": f"Bing – {t['name']} – {GROUP_NAMES[gid]} ({n // 6 + 1})",
                             "url": f"https://www.bing.com/news/search?q={bq}&format=rss&count=50&qft=interval%3d%228%22"})
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
        if src is None:   # Bing: <News:Source>
            src = next((c for c in it if c.tag.endswith("}Source")), None)
        link = it.findtext("link", "")
        if "bing.com/news/apiclick" in link:   # Bing bọc link gốc trong tham số url=
            link = urllib.parse.parse_qs(urllib.parse.urlparse(link).query).get("url", [link])[0]
        items.append({
            "title": it.findtext("title", ""),
            "link": link,
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
    by_title = {norm_title(i["title"]): i for i in by_id.values()}
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
            visa_re = (tax[s["country"]]["visas"][s["visa"]]["re"] if s.get("visa")
                       else tax[s["country"]].get("groups", {}).get(s.get("group"), {}).get("re", []))
            if (s["type"] == "news" or s.get("filter")) and not (GENERAL.search(title) or matches(visa_re, title)):
                continue
            d = parse_date(e["date"]) or now
            if d < cutoff:
                continue
            iid = hashlib.sha1(e["link"].encode()).hexdigest()[:16]
            nt = norm_title(title)
            # Google News chỉ có tiêu đề; nguồn khác (Bing, trang chính phủ) có đoạn tóm tắt thật
            summary = "" if "news.google.com" in s["url"] else clean(e["summary"], 240)
            if iid in by_id or nt in by_title:
                old = by_id.get(iid) or by_title.get(nt)
                if summary and not old.get("summary"):      # bổ sung tóm tắt cho tin đã có từ Google News
                    old["summary"] = summary
                continue
            by_id[iid] = {
                "id": iid,
                "src_group": s.get("group"),
                "src_country": s["country"],
                "title": title,
                "link": e["link"].strip(),
                "summary": summary,
                "publisher": e["publisher"] or s["name"],
                "country": s["country"],
                "type": s["type"],
                "source": s["id"],
                "published": d.isoformat(),
                "fetched": now.isoformat(),
            }
            by_title[nt] = by_id[iid]
            added += 1

    # Gắn nhãn lại toàn bộ, để sửa keywords.json là áp dụng ngay cho cả tin cũ
    pr = load_priority()
    try:
        ai = json.loads((OUT.parent / "ai_labels.json").read_text("utf-8"))
    except Exception:
        ai = {}
    items = [score(tag(i, tax), tax, pr, ai) for i in by_id.values()
             if parse_date(i["published"]) >= cutoff and not EXCLUDE.search(i["title"])]
    items.sort(key=lambda i: i["published"], reverse=True)
    taxonomy = {c: {"name": t["name"], "flag": t["flag"],
                    "visas": {vid: v["name"] for vid, v in t["visas"].items()},
                    "prio": [vid for vid, v in t["visas"].items() if v["prio"]],
                    "groups": {gid: g["name"] for gid, g in t.get("groups", {}).items()}} for c, t in tax.items()}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"updated": now.isoformat(), "taxonomy": taxonomy, "sources": status,
                               "items": items}, ensure_ascii=False, indent=1), "utf-8")
    print(f"Thêm {added} tin mới, tổng {len(items)} tin, {sum(1 for i in items if i['visas'])} tin có nhãn visa.")


if __name__ == "__main__":
    main()

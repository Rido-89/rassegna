import json, html, re, os, sys, urllib.request
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

UA = {"User-Agent": "Mozilla/5.0 (rassegna-bot)"}
ATOM = "{http://www.w3.org/2005/Atom}"
DC = "{http://purl.org/dc/elements/1.1/}"

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

def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(s or ""))).strip()

def fetch(feed):
    try:
        raw = urllib.request.urlopen(urllib.request.Request(feed["url"], headers=UA), timeout=20).read()
        root = ET.fromstring(raw)
    except Exception as e:
        print(f"SALTATO {feed['name']} ({feed['url']}): {e}", file=sys.stderr)
        return []
    rows = []
    for it in root.iter("item"):
        rows.append((it.findtext("title"), (it.findtext("link") or "").strip(),
                     it.findtext("pubDate") or it.findtext(DC + "date"),
                     it.findtext("description")))
    for en in root.iter(ATOM + "entry"):
        l = en.find(ATOM + "link")
        rows.append((en.findtext(ATOM + "title"), l.get("href") if l is not None else "",
                     en.findtext(ATOM + "published") or en.findtext(ATOM + "updated"),
                     en.findtext(ATOM + "summary")))
    out = []
    for title, link, date, desc in rows:
        d = parse_date(date)
        if title and link and d:
            out.append({"title": clean(title), "link": link, "date": d,
                        "source": feed["name"], "text": clean(title + " " + (desc or ""))})
    return out

def make_matcher(words):
    if not words:
        return lambda t: False
    return re.compile(r"\b(?:" + "|".join(re.escape(w) for w in words) + ")", re.I).search

def main():
    cfg = json.load(open("feeds.json", encoding="utf-8"))
    match = make_matcher(cfg.get("keywords", []))
    excluded = make_matcher(cfg.get("exclude", []))
    now = datetime.now(timezone.utc)
    limit = now - timedelta(hours=cfg.get("max_age_hours", 72))
    sections = []
    for cat in cfg["categories"]:
        feeds = cat["feeds"]
        with ThreadPoolExecutor(8) as ex:
            lists = list(ex.map(fetch, feeds))
        items, seen = [], set()
        for feed, lst in zip(feeds, lists):
            for i in lst:
                if not (limit <= i["date"] <= now + timedelta(hours=1)):
                    continue
                if feed.get("filter") and not match(i["text"]):
                    continue
                if excluded(i["text"]) or i["link"] in seen:
                    continue
                seen.add(i["link"])
                items.append(i)
        items.sort(key=lambda i: i["date"], reverse=True)
        rows = "".join(
            f'<li><time datetime="{i["date"].isoformat()}"></time>'
            f'<a href="{html.escape(i["link"], quote=True)}" rel="noopener">{html.escape(i["title"])}</a>'
            f'<span class="src">{html.escape(i["source"])}</span></li>'
            for i in items[:cfg.get("per_category", 20)]
        ) or '<li class="vuoto">Nessuna notizia recente.</li>'
        sections.append(f'<section><h2>{html.escape(cat["name"])}</h2><ul>{rows}</ul></section>')
    stamp = datetime.now(ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y alle %H:%M")
    page = open("template.html", encoding="utf-8").read()
    page = page.replace("%%BODY%%", "\n".join(sections)).replace("%%UPDATED%%", stamp)
    os.makedirs("public", exist_ok=True)
    open("public/index.html", "w", encoding="utf-8").write(page)

if __name__ == "__main__":
    main()

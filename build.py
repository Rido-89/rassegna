import json, html, re, os, sys, urllib.request
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

UA = {"User-Agent": "Mozilla/5.0 (rassegna-bot)"}
ATOM = "{http://www.w3.org/2005/Atom}"
DC = "{http://purl.org/dc/elements/1.1/}"
MEDIA = "{http://search.yahoo.com/mrss/}"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}encoded"
IMG_TAG = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.I)

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

def good_url(u):
    u = (u or "").strip()
    if u.startswith("//"):
        u = "https:" + u
    if u.startswith("http://"):
        u = "https://" + u[7:]
    return u if u.startswith("https://") else ""

def find_image(el, raw_html):
    for tag in ("enclosure", MEDIA + "content", MEDIA + "thumbnail", ATOM + "link"):
        for e in el.iter(tag):
            kind = (e.get("type") or e.get("medium") or "").lower()
            url = e.get("url") or (e.get("href") if tag == ATOM + "link" and e.get("rel") == "enclosure" else None)
            if url and (kind.startswith("image") or kind == "" and tag == MEDIA + "thumbnail"
                        or re.search(r"\.(jpe?g|png|webp)(\?|$)", url, re.I)):
                u = good_url(url)
                if u:
                    return u
    m = IMG_TAG.search(html.unescape(raw_html or ""))
    return good_url(m.group(1)) if m else ""

def fetch(feed):
    try:
        raw = urllib.request.urlopen(urllib.request.Request(feed["url"], headers=UA), timeout=20).read()
        root = ET.fromstring(raw)
    except Exception as e:
        print(f"SALTATO {feed['name']} ({feed['url']}): {e}", file=sys.stderr)
        return []
    rows = []
    for it in root.iter("item"):
        desc = it.findtext("description") or ""
        body = it.findtext(CONTENT) or ""
        rows.append((it, it.findtext("title"), (it.findtext("link") or "").strip(),
                     it.findtext("pubDate") or it.findtext(DC + "date"), desc, desc + body))
    for en in root.iter(ATOM + "entry"):
        l = en.find(ATOM + "link")
        desc = en.findtext(ATOM + "summary") or ""
        body = en.findtext(ATOM + "content") or ""
        rows.append((en, en.findtext(ATOM + "title"), l.get("href") if l is not None else "",
                     en.findtext(ATOM + "published") or en.findtext(ATOM + "updated"), desc, desc + body))
    out = []
    for el, title, link, date, desc, html_all in rows:
        d = parse_date(date)
        if title and link and d:
            out.append({"title": clean(title), "link": link, "date": d, "source": feed["name"],
                        "image": find_image(el, html_all), "text": clean(title + " " + desc)})
    return out

def make_matcher(words):
    if not words:
        return lambda t: False
    return re.compile(r"\b(?:" + "|".join(re.escape(w) for w in words) + ")", re.I).search

def render(i):
    thumb = ""
    if i["image"]:
        thumb = (f'<span class="thumb"><img src="{html.escape(i["image"], quote=True)}" alt="" '
                 f'loading="lazy" referrerpolicy="no-referrer" onerror="this.parentNode.remove()"></span>')
    return (f'<li><a class="card" href="{html.escape(i["link"], quote=True)}" rel="noopener">'
            f'<span class="body"><span class="meta"><b>{html.escape(i["source"])}</b>'
            f'<time datetime="{i["date"].isoformat()}"></time></span>'
            f'<span class="title">{html.escape(i["title"])}</span></span>{thumb}</a></li>')

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
        rows = "".join(render(i) for i in items[:cfg.get("per_category", 20)]) \
            or '<li class="vuoto">Nessuna notizia recente.</li>'
        sections.append(f'<section><h2>{html.escape(cat["name"])}</h2><ul>{rows}</ul></section>')
    stamp = datetime.now(ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y alle %H:%M")
    page = open("template.html", encoding="utf-8").read()
    page = page.replace("%%BODY%%", "\n".join(sections)).replace("%%UPDATED%%", stamp)
    os.makedirs("public", exist_ok=True)
    open("public/index.html", "w", encoding="utf-8").write(page)

if __name__ == "__main__":
    main()

import json, html, re, os, sys, urllib.request
from urllib.parse import urljoin, urlparse
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


OG = re.compile(r"<meta[^>]+(?:property|name)=[\"'](?:og:image|twitter:image)[\"'][^>]*>", re.I)
CONTENT_ATTR = re.compile(r"content=[\"']([^\"']+)[\"']", re.I)
STOP = set("""della delle dello degli dalla dalle nella nelle negli nello sono stato stata dopo anni anno come dove
quando perche perché tutti tutto questo questa nuovo nuova ecco oggi ieri sulla sulle sugli dagli alla alle allo agli
anche contro verso senza sotto sopra tra fra napoli napoletano napoletana napoletani vesuvio vesuviano vesuviana
campania italia italiano video foto news ultime ultima ultimo dalla nell sull dell""".split())

def og_image(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; rassegna-bot)"})
        data = urllib.request.urlopen(req, timeout=8).read(250000).decode("utf-8", "ignore")
    except Exception:
        return ""
    for m in OG.finditer(data):
        c = CONTENT_ATTR.search(m.group(0))
        if c:
            return good_url(urljoin(url, html.unescape(c.group(1))))
    return ""

def host(url):
    h = urlparse(url).netloc.lower()
    return h[4:] if h.startswith("www.") else h

def tokens(title):
    return {w[:6] for w in re.findall(r"[a-zàèéìòù]{4,}", title.lower()) if w not in STOP}

def find_coverage(item, ref_items):
    a = tokens(item["title"])
    best, best_score = None, 0
    for r in ref_items:
        b = tokens(r["title"])
        shared = len(a & b)
        if shared >= 3 and min(len(a), len(b)) and shared / min(len(a), len(b)) >= 0.45:
            score = shared / min(len(a), len(b))
            if score > best_score:
                best, best_score = r, score
    return best

def make_matcher(words):
    if not words:
        return lambda t: False
    return re.compile(r"\b(?:" + "|".join(re.escape(w) for w in words) + ")", re.I).search

def render(i, ref):
    thumb = ""
    if i["image"]:
        thumb = (f'<span class="thumb"><img src="{html.escape(i["image"], quote=True)}" alt="" '
                 f'loading="lazy" referrerpolicy="no-referrer" onerror="this.parentNode.remove()"></span>')
    h = host(i["link"])
    logo = (f'<img class="logo" src="https://www.google.com/s2/favicons?domain={html.escape(h)}&sz=64" alt="" '
            f'width="18" height="18" loading="lazy" onerror="this.remove()">') if h else ""
    cov = ""
    if ref is not None and host(i["link"]) != ref["host"]:
        m = find_coverage(i, ref["items"])
        if m:
            cov = (f'<div class="cov yes"><a href="{html.escape(m["link"], quote=True)}" rel="noopener">'
                   f'Già coperta da {html.escape(ref["name"])}: {html.escape(m["title"])}</a></div>')
        else:
            cov = f'<div class="cov no">Non ancora su {html.escape(ref["name"])}</div>'
    return (f'<li><a class="card" href="{html.escape(i["link"], quote=True)}" rel="noopener">'
            f'<span class="body"><span class="meta">{logo}<b>{html.escape(i["source"])}</b>'
            f'<time datetime="{i["date"].isoformat()}"></time></span>'
            f'<span class="title">{html.escape(i["title"])}</span></span>{thumb}</a>{cov}</li>')

def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

def main():
    cfg = json.load(open("feeds.json", encoding="utf-8"))
    secs = cfg["sections"]
    for sec in secs:
        sec["_match"] = make_matcher(sec.get("keywords", []))
        sec["_excl"] = make_matcher(sec.get("exclude", []))
    by_priority = sorted(secs, key=lambda x: x.get("priority", 99))
    now = datetime.now(timezone.utc)
    limit = now - timedelta(hours=cfg.get("max_age_hours", 72))
    ref, note = None, ""
    rc = cfg.get("reference")
    if rc:
        rlimit = now - timedelta(days=rc.get("days", 7))
        ritems = [i for i in fetch({"name": rc["name"], "url": rc["url"]}) if i["date"] >= rlimit]
        if ritems:
            ref = {"name": rc["name"], "items": ritems, "host": host(rc["url"])}
        else:
            note = f" Confronto con {html.escape(rc['name'])} non disponibile in questo aggiornamento."
    feeds = cfg["feeds"]
    with ThreadPoolExecutor(8) as ex:
        lists = list(ex.map(fetch, feeds))
    buckets = {sec["name"]: [] for sec in secs}
    seen = set()
    for feed, lst in zip(feeds, lists):
        only = make_matcher(feed["only"]) if feed.get("only") else None
        for i in lst:
            if i["link"] in seen or not (limit <= i["date"] <= now + timedelta(hours=1)):
                continue
            if only:
                name = feed.get("default") if only(i["text"]) else None
            else:
                name = next((x["name"] for x in by_priority
                             if x["_match"](i["text"]) and not x["_excl"](i["text"])), None) or feed.get("default")
            if name in buckets:
                seen.add(i["link"])
                buckets[name].append(i)
    limit_n = cfg.get("per_section", 15)
    for name in buckets:
        buckets[name].sort(key=lambda i: i["date"], reverse=True)
        buckets[name] = buckets[name][:limit_n]
    missing = [i for lst in buckets.values() for i in lst if not i["image"]]
    with ThreadPoolExecutor(10) as ex:
        for i, img in zip(missing, ex.map(lambda x: og_image(x["link"]), missing)):
            i["image"] = img
    sections, nav = [], []
    for sec in secs:
        items = buckets[sec["name"]]
        rows = "".join(render(i, ref if sec.get("compare") else None) for i in items) \
            or '<li class="vuoto">Nessuna notizia recente.</li>'
        sid = slug(sec["name"])
        nav.append(f'<a href="#{sid}">{html.escape(sec["name"])}</a>')
        sections.append(f'<section id="{sid}"><h2>{html.escape(sec["name"])}</h2><ul>{rows}</ul></section>')
    stamp = datetime.now(ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y alle %H:%M")
    page = open("template.html", encoding="utf-8").read()
    page = (page.replace("%%NAV%%", "".join(nav)).replace("%%BODY%%", "\n".join(sections))
            .replace("%%UPDATED%%", stamp + "." + note if note else stamp))
    os.makedirs("public", exist_ok=True)
    open("public/index.html", "w", encoding="utf-8").write(page)

if __name__ == "__main__":
    main()

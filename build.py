#!/usr/bin/env python3
"""
Builds whatalgomissed.com from the files in content/ into _site/.
No dependencies — plain Python 3. Run:  python3 build.py
"""
import os, re, json, shutil, html, datetime
from collections import defaultdict, Counter

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "_site")
SITE_URL = "https://whatalgomissed.com"
import json as _json
try:
    FRAMES = _json.load(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)),"content","frames.json"),encoding="utf-8"))
except FileNotFoundError:
    FRAMES = {}
import hashlib as _h
CSS_V = _h.md5(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)),"assets","style.css"),"rb").read()).hexdigest()[:8]
SITE_NAME = "What Algo Missed"
GA_ID = "G-7FZWVPCVL4"
LETTERBOXD = "https://letterboxd.com/nikolitso/"

# ───────────────────────── helpers ─────────────────────────

def esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)

def slugify(t):
    t = str(t).lower()
    t = (t.replace("ά", "α").replace("έ", "ε").replace("ή", "η").replace("ί", "ι")
          .replace("ό", "ο").replace("ύ", "υ").replace("ώ", "ω"))
    t = re.sub(r"[^\w\s-]", "", t, flags=re.U)
    return re.sub(r"[\s_-]+", "-", t).strip("-")

def stars(r):
    try:
        r = float(r)
    except (TypeError, ValueError):
        return ""
    return "★" * int(r) + ("½" if r % 1 else "")

# ── tiny YAML-frontmatter reader (covers what the editor writes) ──

def _scalar(v):
    v = v.strip()
    if v == "" or v in ("~", "null"):
        return None
    if v[0] == '"' and v[-1] == '"' and len(v) >= 2:
        try:
            return json.loads(v)
        except Exception:
            return v[1:-1]
    if v[0] == "'" and v[-1] == "'" and len(v) >= 2:
        return v[1:-1].replace("''", "'")
    if v in ("true", "false"):
        return v == "true"
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    if re.fullmatch(r"-?\d+\.\d+", v):
        return float(v)
    return v

def _flow_list(v):
    inner = v.strip()[1:-1].strip()
    if not inner:
        return []
    items, cur, qch = [], "", None
    for ch in inner:
        if qch:
            cur += ch
            if ch == qch:
                qch = None
        elif ch in "\"'":
            qch = ch; cur += ch
        elif ch == ",":
            items.append(cur); cur = ""
        else:
            cur += ch
    items.append(cur)
    return [_scalar(i) for i in items if i.strip()]

def parse_frontmatter(text):
    text = text.replace("\r\n", "\n")
    if not text.startswith("---"):
        return {}, text
    parts = text.split("\n---", 1)
    head = parts[0][3:].strip("\n")
    body = parts[1].split("\n", 1)[1] if len(parts) > 1 and "\n" in parts[1] else ""
    data, lines, i = {}, head.split("\n"), 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", line)
        if not m:
            i += 1; continue
        key, val = m.group(1), m.group(2)
        if val in ("|", "|-", ">", ">-", "|+", ">+"):
            block = []
            i += 1
            while i < len(lines) and (lines[i].startswith(" ") or lines[i] == ""):
                block.append(lines[i].strip()); i += 1
            data[key] = ("\n" if val.startswith("|") else " ").join(block).strip()
            continue
        if val.strip() == "":
            items = []
            i += 1
            while i < len(lines) and re.match(r"^\s*-\s", lines[i] + " "):
                items.append(_scalar(re.sub(r"^\s*-\s?", "", lines[i]))); i += 1
            data[key] = items if items else None
            continue
        if val.strip().startswith("[") and val.strip().endswith("]"):
            data[key] = _flow_list(val)
        else:
            data[key] = _scalar(val)
        i += 1
    return data, body.strip()

def as_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if x is not None and str(x).strip()]
    return [s.strip() for s in str(v).split(",") if s.strip()]

# ── tiny markdown renderer ──

def md_inline(t):
    t = esc(t)
    t = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", r'<img src="\2" alt="\1" loading="lazy">', t)
    t = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"__(.+?)__", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<em>\1</em>", t)
    t = re.sub(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", r"<em>\1</em>", t)
    t = t.replace("  \n", "<br>").replace("\\\n", "<br>")
    return t

def md(text):
    if not text:
        return ""
    text = text.replace("\r\n", "\n").strip()
    if re.match(r"^\s*<(p|div|h\d|ul|ol|blockquote|figure)[\s>]", text):
        return text  # already HTML (editor in HTML mode)
    out = []
    for block in re.split(r"\n\s*\n", text):
        b = block.strip()
        if not b:
            continue
        if b.startswith("<"):
            out.append(b); continue
        h = re.match(r"^(#{1,4})\s+(.*)$", b)
        if h:
            n = len(h.group(1)) + 1
            out.append(f"<h{n}>{md_inline(h.group(2))}</h{n}>"); continue
        if all(re.match(r"^\s*[-*]\s", l) for l in b.split("\n")):
            items = "".join("<li>" + md_inline(re.sub(r"^\s*[-*]\s", "", l)) + "</li>" for l in b.split("\n"))
            out.append(f"<ul>{items}</ul>"); continue
        if all(l.startswith(">") for l in b.split("\n")):
            inner = "\n".join(re.sub(r"^>\s?", "", l) for l in b.split("\n"))
            out.append(f"<blockquote><p>{md_inline(inner)}</p></blockquote>"); continue
        out.append(f"<p>{md_inline(b)}</p>")
    return "\n".join(out)

def plain(text, n=None):
    t = re.sub(r"<[^>]+>", "", md(text))
    t = html.unescape(re.sub(r"\s+", " ", t)).strip()
    if n and len(t) > n:
        t = t[: n - 1].rsplit(" ", 1)[0] + "…"
    return t

def first_sentence(text, n=220):
    t = plain(text)
    s = re.split(r"(?<=[.!?])\s", t)[0]
    return s if len(s) <= n else plain(text, n)

def youtube_id(v):
    if not v:
        return None
    v = str(v).strip()
    m = re.search(r"(?:v=|youtu\.be/|embed/|shorts/|vi/)([A-Za-z0-9_-]{11})", v)
    if m:
        return m.group(1)
    return v if re.fullmatch(r"[A-Za-z0-9_-]{11}", v) else None

# ───────────────────────── load content ─────────────────────────

def load_dir(path):
    items = []
    d = os.path.join(ROOT, path)
    if not os.path.isdir(d):
        return items
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".md"):
            continue
        with open(os.path.join(d, fn), encoding="utf-8") as fh:
            meta, body = parse_frontmatter(fh.read())
        meta["_file"] = fn
        meta["_slug"] = slugify(meta.get("slug") or fn[:-3])
        meta["body"] = body
        items.append(meta)
    return items

LISTS = sorted(load_dir("content/lists"), key=lambda l: (l.get("order") or 99, l.get("title", "")))
for l in LISTS:
    l["slug"] = l["_slug"]
LIST_BY_NAME = {l["title"].strip().lower(): l for l in LISTS}

FILMS = []
for f in load_dir("content/films"):
    if f.get("draft") is True or not f.get("title"):
        continue
    f["slug"] = f["_slug"]
    try:
        f["year"] = int(f.get("year") or 0)
    except ValueError:
        f["year"] = 0
    try:
        f["rating"] = float(f.get("rating") or 0)
    except ValueError:
        f["rating"] = 0.0
    f["lists"] = as_list(f.get("lists"))
    f["festivals"] = as_list(f.get("festivals"))
    f["awards"] = as_list(f.get("awards"))
    f["country"] = str(f.get("country") or "").strip()
    f["countries"] = [c.strip() for c in re.split(r"[/,·]", f["country"]) if c.strip()]
    f["decade"] = f"{f['year'] // 10 * 10}s" if f["year"] else ""
    f["must_see"] = f["rating"] >= 4.5
    f["yt"] = youtube_id(f.get("trailer"))
    img = (f.get("image") or "").strip() if isinstance(f.get("image"), str) else ""
    if img:
        f["img"] = img; f["img_fb"] = img
    elif f["yt"]:
        fr = FRAMES.get(f["slug"], {})
        f["img_yt"] = fr.get("yt") or f["yt"]
        f["frame_card"] = int(fr.get("card", 1)); f["frame_still"] = int(fr.get("still", 2))
        f["img"] = f"https://i.ytimg.com/vi/{f['img_yt']}/maxres{f['frame_card']}.jpg"
        f["img_fb"] = f"https://i.ytimg.com/vi/{f['img_yt']}/hq{f['frame_card']}.jpg"
    else:
        f["img"] = f["img_fb"] = "/assets/placeholder.svg"
    f["added"] = str(f.get("added") or "2000-01-01")
    f["url"] = f"/films/{f['slug']}/"
    f["excerpt"] = first_sentence(f["body"])
    FILMS.append(f)

def by_year(fs):
    return sorted(fs, key=lambda f: (-f["year"], -f["rating"], f["title"]))

def by_rating(fs):
    return sorted(fs, key=lambda f: (-f["rating"], -f["year"], f["title"]))

def by_added(fs):
    return sorted(fs, key=lambda f: (f["added"], f["year"], f["rating"]), reverse=True)

FILMS = by_year(FILMS)

_used_covers = set()
for l in LISTS:
    l["films"] = by_year([f for f in FILMS if l["title"].lower() in [x.lower() for x in f["lists"]]])
    l["url"] = f"/lists/{l['slug']}/"
    # cover: top-rated film with a trailer frame (no uploaded posters, which often carry title text),
    # and never the same film on two list covers
    ranked = by_rating(l["films"])
    pool = [f for f in ranked if f["yt"] and not (f.get("image") or "").strip() and f["slug"] not in _used_covers] \
        or [f for f in ranked if f["slug"] not in _used_covers] or ranked
    hero = pool[:1]
    if hero:
        _used_covers.add(hero[0]["slug"])
    l["img"], l["img_fb"] = (hero[0]["img"], hero[0]["img_fb"]) if hero else ("/assets/placeholder.svg",) * 2

COUNTRIES = defaultdict(list)
DECADES = defaultdict(list)
FESTIVALS = defaultdict(list)
for f in FILMS:
    for c in f["countries"]:
        COUNTRIES[c].append(f)
    if f["decade"]:
        DECADES[f["decade"]].append(f)
    for fe in f["festivals"]:
        FESTIVALS[fe].append(f)
MUST_SEE = by_rating([f for f in FILMS if f["must_see"]])

# ───────────────────────── templates ─────────────────────────

NAV = [("Films", "/films/"), ("Lists", "/lists/"), ("Browse", "/browse/"),
       ("Film Finder", "/finder/"), ("By Year", "/by-year/"), ("Awards", "/awards/"), ("About", "/about/")]

def layout(title, body, path, desc="", image=None, extra_head="", dark_hero=False):
    full_title = f"{title} — {SITE_NAME}" if title and title != SITE_NAME else SITE_NAME
    desc = desc or "A personal map of world cinema — Greek, Italian, Danish, Iranian, Middle Eastern and beyond. Curated lists with a write-up and a trailer for every film."
    image = image or (SITE_URL + "/assets/og.jpg")
    if image.startswith("/"):
        image = SITE_URL + image
    nav = "".join(
        f'<a href="{u}"{" aria-current=page" if path.startswith(u) else ""}>{n}</a>' for n, u in NAV)
    year = datetime.date.today().year
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(full_title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{SITE_URL}{path}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{esc(SITE_NAME)}">
<meta property="og:title" content="{esc(title or SITE_NAME)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:image" content="{esc(image)}">
<meta property="og:url" content="{SITE_URL}{path}">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Playfair+Display:ital,wght@0,400;0,700;0,800;1,400;1,700&family=Source+Serif+4:ital,opsz,wght@0,8..60,300;0,8..60,400;0,8..60,600;1,8..60,400&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/style.css?v={CSS_V}">
<script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','{GA_ID}');</script>
<script>function fbimg(i,e){{if(i.dataset.done)return;if(e||(i.naturalWidth&&i.naturalWidth<=120)){{i.dataset.done=1;i.src=i.dataset.fb;}}}}</script>
{extra_head}
</head>
<body{' class="has-dark-hero"' if dark_hero else ''}>
<header class="site-head">
  <div class="wrap head-inner">
    <a class="logo" href="/">What Algo <em>Missed</em></a>
    <button class="menu-btn" aria-label="Menu" onclick="document.body.classList.toggle('menu-open')"><span></span><span></span></button>
    <nav class="nav">{nav}</nav>
  </div>
</header>
<main>
{body}
</main>
<footer class="site-foot">
  <div class="wrap foot-inner">
    <div>
      <div class="foot-logo">What Algo Missed</div>
      <p class="foot-note">A personal map of world cinema. The write-ups are my own; the ratings come from my <a href="{LETTERBOXD}">Letterboxd</a>.</p>
    </div>
    <nav class="foot-nav">{nav}<a href="{LETTERBOXD}">Letterboxd</a></nav>
  </div>
</footer>
</body>
</html>"""

def img_tag(src, fb, alt="", cls="", eager=False):
    return (f'<img class="{cls}" src="{esc(src)}" data-fb="{esc(fb)}" alt="{esc(alt)}" '
            f'{"" if eager else "loading=lazy "}decoding="async" onload="fbimg(this)" onerror="fbimg(this,1)">')

def card(f, show_list=True, note=""):
    lst = f["lists"][0] if f["lists"] and show_list else ""
    data = (f'data-title="{esc(f["title"].lower())} {esc((f.get("original_title") or "").lower())} {esc(str(f.get("director") or "").lower())}" '
            f'data-lists="{esc("|".join(slugify(x) for x in f["lists"]))}" '
            f'data-country="{esc("|".join(slugify(c) for c in f["countries"]))}" '
            f'data-decade="{esc(f["decade"])}" data-year="{f["year"]}" data-rating="{f["rating"]}" data-added="{esc(f["added"])}"')
    badge = '<span class="badge">Must see</span>' if f["must_see"] else ""
    return f"""<a class="card" href="{f['url']}" {data}>
  <div class="card-img">{img_tag(f['img'], f['img_fb'], f['title'])}{badge}</div>
  <div class="card-body">
    <div class="card-meta">{esc(f['country'])} · {f['year']}</div>
    <h3 class="card-title">{esc(f['title'])}</h3>
    {f'<div class="card-award">{esc(note)}</div>' if note else ''}
    <div class="card-foot"><span class="stars">{stars(f['rating'])}</span>{f'<span class="card-list">{esc(lst)}</span>' if lst else ''}</div>
  </div>
</a>"""

def grid(films, show_list=True, cls=""):
    return f'<div class="grid {cls}">' + "\n".join(card(f, show_list) for f in films) + "</div>"

def page_head(kicker, title, sub="", count=None, intro_html="", extra=""):
    cnt = f'<div class="ph-count">{count} film{"s" if count != 1 else ""}</div>' if count is not None else ""
    return f"""<section class="page-head">
  <div class="wrap">
    <div class="kicker">{esc(kicker)}</div>
    <h1 class="ph-title">{title}</h1>
    {f'<p class="ph-sub">{esc(sub)}</p>' if sub else ''}
    {cnt}
    {f'<div class="ph-intro prose">{intro_html}</div>' if intro_html else ''}
    {extra}
  </div>
</section>"""

def chip(label, url, n=None, strong=False):
    c = f' <span class="chip-n">{n}</span>' if n is not None else ""
    return f'<a class="chip{" chip-strong" if strong else ""}" href="{url}">{esc(label)}{c}</a>'

# ───────────────────────── page builders ─────────────────────────

pages = {}  # path -> html

def write(path, content):
    pages[path] = content

def country_url(c): return f"/country/{slugify(c)}/"
def decade_url(d): return f"/decade/{d}/"
def festival_url(fe): return f"/festival/{slugify(fe)}/"
def list_url(name):
    l = LIST_BY_NAME.get(name.lower())
    return l["url"] if l else f"/lists/{slugify(name)}/"

# ── home ──
def build_home():
    hero_film = MUST_SEE[0] if MUST_SEE else (FILMS[0] if FILMS else None)
    countries = len(COUNTRIES)
    hero_bg = img_tag(hero_film["img"], hero_film["img_fb"], "", "hero-bg", eager=True) if hero_film else ""
    list_cards = "\n".join(f"""<a class="list-card" href="{l['url']}">
  <div class="list-img">{img_tag(l['img'], l['img_fb'], l['title'])}</div>
  <div class="list-body">
    <div class="list-n">{len(l['films'])} films</div>
    <h3>{esc(l['title'])}</h3>
    <p>{esc(l.get('tagline') or '')}</p>
  </div>
</a>""" for l in LISTS if l["films"])
    recent = by_added(FILMS)[:8]
    body = f"""<section class="hero">
  {hero_bg}
  <div class="hero-shade"></div>
  <div class="wrap hero-inner">
    <div class="rule"></div>
    <div class="kicker">World cinema · Curated film by film</div>
    <h1 class="hero-title">Great films, chosen with care.</h1>
    <p class="hero-sub">Some films take years to find you. These are worth the search: a personal map of world cinema, with a write-up and a trailer for every film.</p>
    <div class="hero-stats"><span><b>{len(FILMS)}</b> films</span><span><b>{countries}</b> countries</span><span><b>{len([l for l in LISTS if l['films']])}</b> lists</span></div>
    <div class="hero-cta"><a class="btn btn-gold" href="/finder/">Find your next film</a><a class="btn btn-ghost" href="/films/">Browse all films</a></div>
  </div>
</section>

<section class="section">
  <div class="wrap">
    <div class="sec-head"><h2>The Lists</h2><a href="/lists/">All lists →</a></div>
    <div class="list-grid">{list_cards}</div>
  </div>
</section>

<section class="section section-alt">
  <div class="wrap">
    <div class="sec-head"><h2>Must See</h2><a href="/must-see/">All {len(MUST_SEE)} →</a></div>
    {grid(MUST_SEE[:8])}
  </div>
</section>

<section class="section">
  <div class="wrap">
    <div class="sec-head"><h2>Recently added</h2><a href="/films/">All {len(FILMS)} films →</a></div>
    {grid(recent)}
  </div>
</section>

<section class="section section-dark">
  <div class="wrap finder-promo">
    <div>
      <div class="kicker">Eight questions</div>
      <h2>Don't know what to watch tonight?</h2>
      <p>Answer eight quick questions about your mood and get three films chosen for this exact moment.</p>
    </div>
    <a class="btn btn-gold" href="/finder/">Start the Film Finder</a>
  </div>
</section>"""
    write("/", layout(SITE_NAME, body, "/", dark_hero=True))

# ── film pages ──
def build_film(f):
    lists_links = " ".join(chip(x, list_url(x), strong=True) for x in f["lists"])
    tags = []
    for c in f["countries"]:
        tags.append(chip(c, country_url(c)))
    if f["decade"]:
        tags.append(chip(f["decade"], decade_url(f["decade"])))
    for fe in f["festivals"]:
        tags.append(chip(fe, festival_url(fe)))
    if f["must_see"]:
        tags.append(chip("Must See", "/must-see/"))
    awards = "".join(f"<li>{esc(a)}</li>" for a in f["awards"])
    trailer = ""
    if f["yt"]:
        yurl = f"https://www.youtube.com/watch?v={f['yt']}"
        _sy = f.get("img_yt") or f["yt"]; _sn = f.get("frame_still", 2)
        still = f"https://i.ytimg.com/vi/{_sy}/maxres{_sn}.jpg"
        still_fb = f"https://i.ytimg.com/vi/{_sy}/hq{_sn}.jpg"
        trailer = f"""<figure class="still">
  <a href="{yurl}" target="_blank" rel="noopener">{img_tag(still, still_fb, f['title'] + ' — still')}</a>
</figure>
<p class="trailer-link"><a href="{yurl}" target="_blank" rel="noopener">▶ Watch the trailer on YouTube ↗</a></p>"""
    # related: same first list, closest rating, excluding self
    rel = []
    if f["lists"]:
        l = LIST_BY_NAME.get(f["lists"][0].lower())
        if l:
            rel = [x for x in by_rating(l["films"]) if x["slug"] != f["slug"]][:3]
    rel_html = ""
    if rel:
        rel_html = f"""<section class="section section-alt"><div class="wrap">
  <div class="sec-head"><h2>More from {esc(f['lists'][0])}</h2><a href="{list_url(f['lists'][0])}">See the list →</a></div>
  {grid(rel, cls='grid-3')}
</div></section>"""
    orig = f'<div class="fh-orig">{esc(f["original_title"])}</div>' if f.get("original_title") else ""
    ld = {
        "@context": "https://schema.org", "@type": "Review",
        "itemReviewed": {"@type": "Movie", "name": f["title"], "dateCreated": str(f["year"]),
                          "director": {"@type": "Person", "name": f.get("director") or ""},
                          "image": f["img_fb"] if f["img_fb"].startswith("http") else SITE_URL + f["img_fb"]},
        "author": {"@type": "Person", "name": "Antonis Nikolitsopoulos"},
        "reviewRating": {"@type": "Rating", "ratingValue": f["rating"], "bestRating": 5, "worstRating": 0.5},
        "reviewBody": plain(f["body"]),
    }
    body = f"""<article>
<section class="film-hero">
  {img_tag(f['img'], f['img_fb'], f['title'], 'fh-img', eager=True)}
  <div class="fh-shade"></div>
  <div class="wrap fh-inner">
    <div class="kicker">{' · '.join(esc(x) for x in f['lists'])}</div>
    <h1 class="fh-title">{esc(f['title'])}</h1>
    {orig}
    <div class="fh-meta"><span>{esc(f.get('director') or '')}</span><span>{esc(f['country'])}</span><span>{f['year']}</span><span class="stars">{stars(f['rating'])}</span></div>
  </div>
</section>
<div class="wrap film-layout">
  <div class="film-main">
    <div class="prose review">{md(f['body'])}</div>
    {trailer}
  </div>
  <aside class="film-side">
    <dl class="facts">
      <dt>Director</dt><dd>{esc(f.get('director') or '—')}</dd>
      <dt>Country</dt><dd>{' / '.join(f'<a href="{country_url(c)}">{esc(c)}</a>' for c in f['countries']) or '—'}</dd>
      <dt>Year</dt><dd><a href="{decade_url(f['decade'])}">{f['year']}</a></dd>
      <dt>My rating</dt><dd class="stars big">{stars(f['rating'])}</dd>
    </dl>
    {f'<div class="side-block"><div class="side-label">Awards</div><ul class="awards">{awards}</ul></div>' if awards else ''}
    <div class="side-block"><div class="side-label">In the lists</div><div class="chips">{lists_links}</div></div>
    <div class="side-block"><div class="side-label">Filed under</div><div class="chips">{''.join(tags)}</div></div>
  </aside>
</div>
</article>
{rel_html}"""
    extra = f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>'
    desc = f"{f['title']} ({f['year']}, {f.get('director') or ''}) — {f['excerpt']}"
    write(f["url"], layout(f"{f['title']} ({f['year']})", body, f["url"], plain(desc, 300), f["img_fb"], extra, dark_hero=True))

# ── category pages ──
def build_category(kicker, title, path, films, sub="", intro_html="", sort=by_year, extra=""):
    body = page_head(kicker, esc(title), sub, len(films), intro_html, extra) + \
        f'<section class="section"><div class="wrap">{grid(sort(films))}</div></section>'
    write(path, layout(title, body, path, sub or f"{title}: {len(films)} films with write-ups and trailers."))

def build_lists():
    for l in LISTS:
        link = ""
        if l.get("link"):
            lab = "Watch on Cinobo" if "cinobo" in l["link"] else "View on Letterboxd"
            link = f'<a class="btn btn-ghost-dark" href="{esc(l["link"])}" target="_blank" rel="noopener">{lab} ↗</a>'
        title = l["title"] + (f" — {l['subtitle']}" if l.get("subtitle") else "")
        body = page_head("The List", esc(l["title"]) + (f' <em>{esc(l["subtitle"])}</em>' if l.get("subtitle") else ""),
                         l.get("tagline") or "", len(l["films"]), md(l["body"]), link) + \
            f'<section class="section"><div class="wrap">{grid(l["films"], show_list=False)}</div></section>'
        write(l["url"], layout(title, body, l["url"], plain(l.get("tagline") or l["body"], 200), l["img_fb"]))
    cards = "\n".join(f"""<a class="list-card" href="{l['url']}">
  <div class="list-img">{img_tag(l['img'], l['img_fb'], l['title'])}</div>
  <div class="list-body"><div class="list-n">{len(l['films'])} films</div><h3>{esc(l['title'])}</h3><p>{esc(l.get('tagline') or '')}</p></div>
</a>""" for l in LISTS if l["films"])
    body = page_head("Curated", "The Lists", "Every list began as a private obsession.") + \
        f'<section class="section"><div class="wrap"><div class="list-grid">{cards}</div></div></section>'
    write("/lists/", layout("The Lists", body, "/lists/"))

def build_taxonomies():
    for c, fs in COUNTRIES.items():
        build_category("Country", c, country_url(c), fs)
    for d, fs in DECADES.items():
        build_category("Decade", d, decade_url(d), fs)
    for fe, fs in FESTIVALS.items():
        build_category("Festivals & Awards", fe, festival_url(fe), fs, f"Films recognised at {fe}.", sort=by_rating)
    build_category("Start here", "Must See", "/must-see/", MUST_SEE,
                   "My highest-rated films — four and a half stars and above.", sort=by_rating)


AWARD_GROUPS = [
    ("oscars", "Oscars & Golden Globes", r"^Oscar\b(?! Nominat)|^\d+ Oscar Nominations · Won|^\d+ Academy Awards|Golden Globe"),
    ("cannes", "Cannes", r"Cannes|Palme|Caméra"),
    ("berlin", "Berlin", r"Berlin|Bear|Teddy"),
    ("venice", "Venice", r"Venice"),
    ("festivals", "Festivals worldwide", r"Sundance|Tribeca|Toronto|TIFF|BFI|Jerusalem|Thessaloniki|Pula|Karlovy|San Sebasti|Locarno|Göteborg"),
    ("national", "National film awards", r"."),
]
_NOT_WIN = r"Nominat|Nominee|Selection|Official|Opening Film|Submission|Entry|Co-production|Guinness|Budapest|Critics' Week|Directors' Fortnight"

def is_award_win(s):
    parts = [p.strip() for p in s.split("·")]
    if any(re.search(r"\bWon\b|^\d+ Wins?$", p) for p in parts):
        return True
    if any(re.match(r"^\d+ .*Awards?$", p) and "Nominat" not in p for p in parts):
        return True
    if re.search(_NOT_WIN, s) or s.strip() in ("Cannes · Un Certain Regard", "Un Certain Regard · Cannes"):
        return False
    return True

def build_awards():
    groups = {k: [] for k, _, _ in AWARD_GROUPS}
    winners = set()
    for f in FILMS:
        for a in f["awards"]:
            if not is_award_win(a):
                continue
            for k, _, rx in AWARD_GROUPS:
                if re.search(rx, a):
                    groups[k].append((f, a)); winners.add(f["slug"]); break
    chips = "".join(f'<a class="chip" href="#{k}">{esc(n)}<span class="chip-n">{len(groups[k])}</span></a>'
                    for k, n, _ in AWARD_GROUPS if groups[k])
    secs = ""
    for k, n, _ in AWARD_GROUPS:
        items = groups[k]
        if not items:
            continue
        items.sort(key=lambda x: (-x[0]["rating"], -x[0]["year"]))
        cards = "\n".join(card(f, True, a) for f, a in items)
        secs += f"""<section class="section{' section-alt' if len(secs) % 2 else ''}" id="{k}">
  <div class="wrap">
    <div class="sec-head"><h2>{esc(n)}</h2><span class="sec-n">{len(items)} award{'s' if len(items) != 1 else ''}</span></div>
    <div class="grid">{cards}</div>
  </div>
</section>"""
    body = page_head("Recognition", "Awards", "", len(winners),
                     "<p>Films in this collection that took home a prize: from the Palme d'Or and the Oscars to the national academies that know their own cinema best.</p>",
                     f'<div class="chips">{chips}</div>') + secs
    write("/awards/", layout("Awards", body, "/awards/", "Award-winning world cinema: Oscars, Cannes, Berlin, Venice and national film awards."))
    return len(winners)

def build_browse():
    def section(h, items):
        return f'<div class="browse-sec"><div class="side-label">{h}</div><div class="chips">{"".join(items)}</div></div>'
    lists = [chip(l["title"], l["url"], len(l["films"]), True) for l in LISTS if l["films"]]
    countries = [chip(c, country_url(c), len(fs)) for c, fs in sorted(COUNTRIES.items(), key=lambda kv: (-len(kv[1]), kv[0]))]
    decades = [chip(d, decade_url(d), len(fs)) for d, fs in sorted(DECADES.items(), reverse=True)]
    fests = [chip(fe, festival_url(fe), len(fs)) for fe, fs in sorted(FESTIVALS.items(), key=lambda kv: -len(kv[1]))]
    body = page_head("Browse", "Find a film your way", "By list, by country, by decade, by festival.") + f"""
<section class="section"><div class="wrap narrow">
  <a class="must-banner" href="/must-see/"><span class="kicker">Start here</span><span class="mb-title">Must See — {len(MUST_SEE)} films →</span></a>
  {section("The Lists", lists)}
  {section("By Country", countries)}
  {section("By Decade", decades)}
  {section("Festivals & Awards", fests)}
  <a class="must-banner alt" href="/finder/"><span class="kicker">Not sure?</span><span class="mb-title">Take the Film Finder →</span></a>
</div></section>"""
    write("/browse/", layout("Browse", body, "/browse/"))

def build_all_films():
    lists_opts = "".join(f'<option value="{l["slug"]}">{esc(l["title"])}</option>' for l in LISTS if l["films"])
    c_opts = "".join(f'<option value="{slugify(c)}">{esc(c)} ({len(fs)})</option>' for c, fs in sorted(COUNTRIES.items()))
    d_opts = "".join(f'<option value="{d}">{d}</option>' for d in sorted(DECADES, reverse=True))
    filters = f"""<div class="filters" id="filters">
  <input type="search" id="q" placeholder="Search title or director…" aria-label="Search">
  <select id="fl" aria-label="List"><option value="">All lists</option>{lists_opts}</select>
  <select id="fc" aria-label="Country"><option value="">All countries</option>{c_opts}</select>
  <select id="fd" aria-label="Decade"><option value="">All decades</option>{d_opts}</select>
  <select id="fs" aria-label="Sort"><option value="year">Newest first</option><option value="old">Oldest first</option><option value="rating">Highest rated</option><option value="added">Recently added</option></select>
  <div class="f-count"><span id="n">{len(FILMS)}</span> films</div>
</div>"""
    script = """<script>
(function(){
 var g=document.querySelector('#all .grid'),cards=[].slice.call(g.children),$=function(i){return document.getElementById(i)};
 var p=new URLSearchParams(location.search);['q','fl','fc','fd','fs'].forEach(function(k){if(p.get(k))$(k).value=p.get(k)});
 function run(){var q=$('q').value.trim().toLowerCase(),l=$('fl').value,c=$('fc').value,d=$('fd').value,s=$('fs').value,n=0;
  cards.sort(function(a,b){var A=a.dataset,B=b.dataset;
   if(s==='rating')return B.rating-A.rating||B.year-A.year;
   if(s==='old')return A.year-B.year;
   if(s==='added')return (B.added>A.added?1:B.added<A.added?-1:0)||B.year-A.year;
   return B.year-A.year||B.rating-A.rating;});
  cards.forEach(function(e){var D=e.dataset,ok=(!q||D.title.indexOf(q)>-1)&&(!l||('|'+D.lists+'|').indexOf('|'+l+'|')>-1)&&(!c||('|'+D.country+'|').indexOf('|'+c+'|')>-1)&&(!d||D.decade===d);
   e.style.display=ok?'':'none';if(ok)n++;g.appendChild(e);});
  $('n').textContent=n;$('empty').style.display=n?'none':'block';
  var u=new URLSearchParams();['q','fl','fc','fd','fs'].forEach(function(k){if($(k).value&&!(k==='fs'&&$(k).value==='year'))u.set(k,$(k).value)});
  history.replaceState(null,'',location.pathname+(u.toString()?'?'+u:''));}
 ['q','fl','fc','fd','fs'].forEach(function(k){$(k).addEventListener('input',run)});run();
})();
</script>"""
    body = page_head("The Archive", "All Films", "Every film on the site, with a write-up and a trailer.", None, "", filters) + \
        f'<section class="section" id="all"><div class="wrap">{grid(FILMS)}<p id="empty" class="empty">No films match — try fewer filters.</p></div></section>' + script
    write("/films/", layout("All Films", body, "/films/"))

def build_by_year():
    years = defaultdict(list)
    for f in FILMS:
        years[f["year"]].append(f)
    out = []
    for y in sorted(years, reverse=True):
        rows = "".join(f"""<a class="yr-row" href="{f['url']}"><span class="stars">{stars(f['rating'])}</span><span class="yr-title">{esc(f['title'])}</span><span class="yr-country">{esc(f['country'])}</span></a>""" for f in by_rating(years[y]))
        out.append(f'<div class="yr-block" id="y{y}"><h2 class="yr">{y}</h2>{rows}</div>')
    jump = "".join(f'<a href="#y{y}">{y}</a>' for y in sorted(years, reverse=True))
    body = page_head("Chronology", "Films by Year", "Ranked by rating within each year.", len(FILMS), "", f'<div class="yr-jump">{jump}</div>') + \
        f'<section class="section"><div class="wrap narrow">{"".join(out)}</div></section>'
    write("/by-year/", layout("Films by Year", body, "/by-year/"))

def build_finder():
    path = os.path.join(ROOT, "content", "finder.json")
    tpl_path = os.path.join(ROOT, "finder_template.html")
    if not (os.path.exists(path) and os.path.exists(tpl_path)):
        return
    fm = {f["slug"]: f for f in FILMS}
    data = []
    for d in json.load(open(path, encoding="utf-8")):
        f = fm.get(d.get("film"))
        if not f:
            continue
        rec = {k: v for k, v in d.items() if k != "film"}
        rec.update(title=f["title"], director=f.get("director") or "", year=f["year"], country=f["country"],
                   award=(f["awards"][0] if f["awards"] else ""), desc=plain(f["body"], 420), url=f["url"],
                   img=f["img"], fb=f["img_fb"])
        data.append(rec)
    tpl = open(tpl_path, encoding="utf-8").read().replace("__FINDER_DATA__", json.dumps(data, ensure_ascii=False))
    body = page_head("Film Finder", "Find your next film", "Eight questions. Three films chosen for this exact moment.") + \
        f'<section class="section finder"><div class="wrap">{tpl}</div></section>'
    write("/finder/", layout("Film Finder", body, "/finder/"))

def build_pages():
    for p in load_dir("content/pages"):
        path = f"/{p['_slug']}/"
        body = page_head("", esc(p.get("title") or ""), p.get("subtitle") or "") + \
            f'<section class="section"><div class="wrap narrow prose about">{md(p["body"])}</div></section>'
        write(path, layout(p.get("title") or "", body, path, plain(p["body"], 200)))

def build_404():
    body = page_head("404", "This reel is missing", "The page you were looking for isn't here.") + \
        '<section class="section"><div class="wrap"><p><a class="btn btn-gold" href="/films/">Browse all films</a></p></div></section>'
    write("/404.html", layout("Not found", body, "/404.html"))

# ───────────────────────── write site ─────────────────────────

def main():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    build_home(); build_all_films(); build_lists(); build_taxonomies(); build_browse()
    build_by_year(); build_finder(); build_pages(); build_404(); build_awards()
    for f in FILMS:
        build_film(f)
    for path, content in pages.items():
        fp = os.path.join(OUT, path.strip("/"), "index.html") if not path.endswith(".html") else os.path.join(OUT, path.strip("/"))
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w", encoding="utf-8") as fh:
            fh.write(content)
    # static files
    for src in ("static", "assets"):
        s = os.path.join(ROOT, src)
        if os.path.isdir(s):
            shutil.copytree(s, os.path.join(OUT, "" if src == "static" else "assets"), dirs_exist_ok=True)
    # sitemap + robots + redirects
    today = datetime.date.today().isoformat()
    urls = "".join(f"<url><loc>{SITE_URL}{p}</loc><lastmod>{today}</lastmod></url>" for p in sorted(pages) if not p.endswith(".html"))
    open(os.path.join(OUT, "sitemap.xml"), "w").write(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>')
    open(os.path.join(OUT, "robots.txt"), "w").write(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")
    # RSS feed of recently added films
    from email.utils import format_datetime
    def _rfc(d):
        try:
            y, m, dd = (int(x) for x in d[:10].split("-"))
            return format_datetime(datetime.datetime(y, m, dd, 9, 0, tzinfo=datetime.timezone.utc))
        except Exception:
            return format_datetime(datetime.datetime.now(datetime.timezone.utc))
    items = "".join(
        f"<item><title>{esc(f['title'])} ({f['year']})</title><link>{SITE_URL}{f['url']}</link>"
        f"<guid>{SITE_URL}{f['url']}</guid><pubDate>{_rfc(f['added'])}</pubDate>"
        f"<description>{esc(f['excerpt'])}</description></item>"
        for f in by_added(FILMS)[:20])
    open(os.path.join(OUT, "feed.xml"), "w", encoding="utf-8").write(
        f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>What Algo Missed</title>'
        f'<link>{SITE_URL}/</link><description>World cinema, chosen with care</description>{items}</channel></rss>')
    redirects = {
        "/feed": "/feed.xml",
        "/danish-cinema-a-personal-map/": "/lists/danish-cinema/",
        "/italia-bel-paese-brutte-storie/": "/lists/italian-cinema/",
        "/iranian-cinema-against-the-wall/": "/lists/iranian-cinema/",
        "/ellada-greek-cinema/": "/lists/greek-cinema/",
        "/middle-eastern-cinema/": "/lists/middle-eastern-cinema/",
        "/europa-european-cinema/": "/lists/europa/",
        "/world-cinema/": "/lists/world-cinema/",
        "/the-game-is-never-just-the-game/": "/lists/sport-cinema/",
        "/cinobo-whats-worth-watching/": "/lists/on-cinobo/",
        "/norden-nordic-cinema/": "/lists/nordic-cinema/",
        "/film-finder/": "/finder/",
        "/films-by-year/": "/by-year/",
        "/tag/*": "/browse/",
    }
    open(os.path.join(OUT, "_redirects"), "w").write("\n".join(f"{a} {b} 301" for a, b in redirects.items()) + "\n")
    print(f"Built {len(pages)} pages · {len(FILMS)} films · {len(LISTS)} lists · {len(COUNTRIES)} countries → _site/")

if __name__ == "__main__":
    main()

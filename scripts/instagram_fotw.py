"""Film of the Week: a 5-slide Instagram carousel every Saturday night.

Usage (in the Action):  python scripts/instagram_fotw.py [--dry-run] [--force]

Slides (1080x1350): 1 cover with a FILM OF THE WEEK label, 2 a quote from the review,
3-4 two more stills, 5 a closing card pointing to the review. Images go to
assets/instagram/fotw/ (Instagram fetches carousel images from public URLs).

Choosing the film: content/film_of_the_week.json holds "queue" (slugs to use first, in order;
edit it to pick a film) and "history" (what has run). Otherwise the next Must See film that
hasn't been Film of the Week. Needs INSTAGRAM_TOKEN, INSTAGRAM_USER_ID and TMDB_TOKEN.
"""
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bluesky_post import film  # noqa: E402
from instagram_card import (flag, name_tags, question, CREAM, DARK, GOLD, MUTED, NATIONAL, W, H, draw_stars, font,  # noqa: E402
                            mark, stars, wrap)
from instagram_post import USER_ID, call, git  # noqa: E402
from instagram_reel_post import stills_for  # noqa: E402
from share_on_x import field, slugify  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FILMS = ROOT / "content" / "films"
STATE = ROOT / "content" / "film_of_the_week.json"
OUT = ROOT / "assets" / "instagram" / "fotw"
PUBLIC = "https://whatalgomissed.com/assets/instagram/fotw/"
UA = {"User-Agent": "whatalgomissed-bot/1.0 (+https://whatalgomissed.com)"}


def load_state():
    s = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    return {"queue": s.get("queue", []), "history": s.get("history", [])}


def save_state(s):
    STATE.write_text(json.dumps(s, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def review_paragraphs(f):
    body = f["text"].replace("\r\n", "\n").split("\n---", 1)[1] if "\n---" in f["text"] else ""
    return [p.strip() for p in body.split("\n\n") if p.strip() and not p.strip().startswith(("<", "#", "!"))]


def sentences(p):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", p) if s.strip()]


def quote_from(f, limit=230):
    """The verdict: the closing sentences of the review (as many as fit), which is where the opinion is."""
    paras = review_paragraphs(f)
    if paras:
        q = ""
        for s in reversed(sentences(paras[-1])):
            if len(q) + len(s) + 1 > limit:
                break
            q = f"{s} {q}".strip()
        if len(q) > 40:
            return q
    return field(f["fm"], "x_post")


def same_image(a, b):
    """True if two files show the same picture (any size or compression)."""
    def thumb(p):
        return Image.open(p).convert("L").resize((32, 18))
    ta, tb = thumb(a), thumb(b)
    diff = sum(abs(x - y) for x, y in zip(ta.tobytes(), tb.tobytes())) / (32 * 18)
    return diff < 14


def fill(still_path):
    im = Image.open(still_path).convert("RGB")
    s = max(W / im.width, H / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    left, top = (im.width - W) // 2, (im.height - H) // 2
    return im.crop((left, top, left + W, top + H))


def shade(img, start=.45, strength=245):
    g = Image.new("L", (1, H))
    for y in range(H):
        g.putpixel((0, y), round(strength * max(0.0, (y - H * start) / (H * (1 - start))) ** 1.25))
    img.paste(Image.new("RGB", (W, H), DARK), (0, 0), g.resize((W, H)))
    return img


def brand_footer(d, color=MUTED):
    mark(d, 66, H - 92, 56)
    b = font("PlayfairDisplay[wght].ttf", 30, 700)
    d.text((132, H - 54), "What Algo ", font=b, fill=CREAM, anchor="ls")
    d.text((132 + d.textlength("What Algo ", font=b), H - 54), "Missed",
           font=font("PlayfairDisplay-Italic[wght].ttf", 30, 400), fill=GOLD, anchor="ls")
    d.text((W - 72, H - 54), "whatalgomissed.com", font=font("IBMPlexMono-Medium.ttf", 22), fill=color, anchor="rs")


def slide_cover(f, still, week):
    fm = f["fm"]
    img = shade(fill(still), .40)
    d = ImageDraw.Draw(img)
    # gold label at the top
    lab = font("IBMPlexMono-Medium.ttf", 30)
    text = "FILM OF THE WEEK"
    tw = d.textlength(text, font=lab)
    d.rectangle([72, 70, 72 + tw + 44, 128], fill=GOLD)
    d.text((94, 99), text, font=lab, fill=DARK, anchor="lm")
    d.text((72 + tw + 70, 99), week, font=font("IBMPlexMono-Medium.ttf", 26), fill=CREAM, anchor="lm")
    title = field(fm, "title")
    size = 104
    while True:
        tf = font("PlayfairDisplay[wght].ttf", size, 800)
        rows = wrap(d, title, tf, W - 144)
        if len(rows) <= 2 or size <= 64:
            break
        size -= 8
    y = H - 390 - (len(rows) - 1) * round(size * 1.08)
    d.text((72, y - 56), f"{field(fm, 'country').upper()} · {field(fm, 'year')}", font=font("IBMPlexMono-Medium.ttf", 28), fill=GOLD)
    for r in rows:
        d.text((72, y), r, font=tf, fill=CREAM)
        y += round(size * 1.08)
    d.text((72, y + 14), f"Directed by {field(fm, 'director')}", font=font("PlayfairDisplay-Italic[wght].ttf", 40, 400), fill=MUTED)
    draw_stars(img, 72, y + 104, float(field(fm, "rating") or 0), 22)
    brand_footer(ImageDraw.Draw(img))
    return img


def slide_quote(f):
    img = Image.new("RGB", (W, H), DARK)
    d = ImageDraw.Draw(img)
    q = quote_from(f)
    d.text((72, 250), "“", font=font("PlayfairDisplay[wght].ttf", 260, 700), fill=GOLD)
    size = 60
    while True:
        qf = font("PlayfairDisplay-Italic[wght].ttf", size, 400)
        rows = wrap(d, q, qf, W - 160)
        if len(rows) * size * 1.3 < 620 or size <= 40:
            break
        size -= 4
    y = 470
    for r in rows:
        d.text((80, y), r, font=qf, fill=CREAM)
        y += round(size * 1.3)
    d.line([(80, y + 40), (160, y + 40)], fill=GOLD, width=3)
    d.text((80, y + 70), "From my review of", font=font("IBMPlexMono-Medium.ttf", 24), fill=MUTED)
    d.text((80, y + 104), field(f["fm"], "title"), font=font("PlayfairDisplay[wght].ttf", 40, 700), fill=CREAM)
    brand_footer(d)
    return img


def slide_still(still):
    img = shade(fill(still), .78, 200)
    brand_footer(ImageDraw.Draw(img), CREAM)
    return img


def slide_end(f):
    img = Image.new("RGB", (W, H), DARK)
    d = ImageDraw.Draw(img)
    mark(d, W // 2 - 60, 330, 120)
    d.text((W // 2, 560), field(f["fm"], "title"), font=font("PlayfairDisplay[wght].ttf", 66, 800), fill=CREAM, anchor="mm")
    draw_stars(img, W // 2 - 128, 650, float(field(f["fm"], "rating") or 0), 26)
    d.line([(W // 2 - 60, 750), (W // 2 + 60, 750)], fill=GOLD, width=2)
    d.text((W // 2, 840), "Full review + trailer", font=font("PlayfairDisplay[wght].ttf", 58, 700), fill=CREAM, anchor="mm")
    d.text((W // 2, 920), "link in bio", font=font("PlayfairDisplay-Italic[wght].ttf", 52, 400), fill=GOLD, anchor="mm")
    d.text((W // 2, 1030), f"whatalgomissed.com/films/{f['slug']}", font=font("IBMPlexMono-Medium.ttf", 28), fill=MUTED, anchor="mm")
    d.text((W // 2, 1110), "A new Film of the Week every Saturday", font=font("IBMPlexMono-Medium.ttf", 24), fill=MUTED, anchor="mm")
    return img


def caption(f):
    fm = f["fm"]
    paras = review_paragraphs(f)
    extract = ""
    for s in sentences(paras[0] if paras else field(fm, "x_post")):
        if len(extract) + len(s) > 520:
            break
        extract = f"{extract} {s}".strip()
    country = field(fm, "country")
    tag = slugify(re.split(r"[,/]", country)[0]).replace("-", "")
    tag = NATIONAL.get(tag, tag)
    rating = float(field(fm, "rating") or 0)
    return (f"FILM OF THE WEEK · {field(fm, 'title')} ({field(fm, 'year')}) {flag(country)} · {country}\n\n"
            f"{extract}\n\n“{quote_from(f)}”\n\n"
            f"Directed by {field(fm, 'director')}\nMy rating: {stars(rating)} ({rating:g}/5)\n\n"
            f"{question(f['slug'])}\n\nFull review and trailer: link in bio\nwhatalgomissed.com/films/{f['slug']}/\n\n"
            f"#filmoftheweek {name_tags(field(fm, 'title'), field(fm, 'director'))} #worldcinema #filmrecommendations #cinephile #{tag}cinema")


# Seasonal relevance: words in the review / summary that tie a film to a time of year
SEASON_WORDS = {
    "winter": r"\b(winter|snow\w*|christmas|xmas|frozen|frost\w*|icy|blizzard|new year|december|freezing|sleigh)\b",
    "spring": r"\b(spring(time)?|blossom\w*|easter|april)\b",
    "summer": r"\b(summer\w*|beach\w*|sun-?drenched|heatwave|swimming|vacation|holiday\w*|august)\b",
    "autumn": r"\b(autumn\w*|harvest|first day of school|school year|september|october)\b",
}
OPPOSITE = {"winter": "summer", "summer": "winter", "spring": "autumn", "autumn": "spring"}
# the big festival/award of each month: films that won there get a boost
MONTH_EVENT = {2: r"berlin|berlinale|golden bear|silver bear", 3: r"oscar|academy award", 5: r"cannes|palme",
               9: r"venice|golden lion|silver lion", 11: r"thessaloniki|golden alexander", 12: r"european film award"}


def season_of(d):
    return {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
            6: "summer", 7: "summer", 8: "summer"}.get(d.month, "autumn")


def relevance(f, today):
    """Higher = better fit for this week. Films clearly set in the opposite season are excluded."""
    text = " ".join([f["text"], field(f["fm"], "logline"), field(f["fm"], "x_post")]).lower()
    season = season_of(today)
    if re.search(SEASON_WORDS[OPPOSITE[season]], text):
        return None, f"set in {OPPOSITE[season]}"
    score, why = 0, []
    hits = len(re.findall(SEASON_WORDS[season], text))
    if hits:
        score += 4 + min(hits, 3)
        why.append(f"fits {season}")
    ev = MONTH_EVENT.get(today.month)
    awards = " ".join(re.findall(r'^\s*-\s*"([^"]+)"', f["fm"], re.M)).lower()
    if ev and re.search(ev, awards):
        score += 3
        why.append("festival of the month")
    return score, ", ".join(why) or "Must See"


def pick(state, today=None):
    today = today or date.today()
    films = {f["slug"]: f for f in (film(p) for p in sorted(FILMS.glob("*.md")))}
    done = {h["slug"] for h in state["history"]}
    for s in state["queue"]:  # your own choice always wins
        if s in films and s not in done:
            return films[s], "chosen by you"
    ranked = []
    for f in films.values():
        if not f["share"] or f["rating"] < 4.5 or f["slug"] in done:
            continue
        score, why = relevance(f, today)
        if score is None:
            continue
        ranked.append((-score, -f["rating"], hashlib.sha256((f["slug"] + str(today)).encode()).hexdigest(), f, why))
    ranked.sort(key=lambda r: r[:3])
    return (ranked[0][3], ranked[0][4]) if ranked else (None, "")


def wait_live(urls):
    for url in urls:
        for _ in range(60):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers=UA), timeout=20) as r:
                    if r.status == 200 and r.headers.get("Content-Type", "").startswith("image/"):
                        break
            except urllib.error.URLError:
                pass
            time.sleep(10)
        else:
            raise SystemExit(f"{url} never went live; not posting")


def wait_ready(container):
    for _ in range(40):
        status = call(container, {"fields": "status_code"}).get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise SystemExit(f"Instagram could not process {container} ({status})")
        time.sleep(5)
    raise SystemExit("Instagram is still processing; giving up")


def main():
    dry, force = "--dry-run" in sys.argv, "--force" in sys.argv
    state = load_state()
    today = date.today()
    if not force and state["history"]:
        last = datetime.strptime(state["history"][-1]["date"], "%Y-%m-%d").date()
        if (today - last).days < 5:
            print("Film of the Week already posted this week")
            return
    f, why = pick(state, today)
    if not f:
        print("no film left")
        return
    print(f"chosen: {f['slug']} ({why})")
    week = f"WEEK OF {(today - timedelta(days=today.weekday())).strftime('%d %b %Y').upper()}"

    with tempfile.TemporaryDirectory() as tmp:
        stills = stills_for(f["slug"], tmp, want=6)
        backdrop = ROOT / "assets" / "backdrops" / f"{f['slug']}.jpg"
        if backdrop.exists():  # the site's chosen still makes the cover; drop TMDB copies of it
            stills = [s for s in stills if not same_image(s, backdrop)]
            stills.insert(0, str(backdrop))
        while len(stills) < 3:
            stills.append(stills[-1] if stills else str(backdrop))
        slides = [slide_cover(f, stills[0], week), slide_quote(f), slide_still(stills[1]),
                  slide_still(stills[2]), slide_end(f)]
    out = OUT if not dry else ROOT / "instagram" / "fotw"
    out.mkdir(parents=True, exist_ok=True)
    names = [f"{f['slug']}-{i + 1}.jpg" for i in range(len(slides))]
    for img, n in zip(slides, names):
        img.save(out / n, quality=90)
    cap = caption(f)
    print(f"--- Film of the Week: {f['slug']}\n{cap}\n")
    if dry:
        print("dry run: slides in", out)
        return

    git("add", *[str(out / n) for n in names])
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode:
        git("commit", "-q", "-m", f"Film of the Week: slides for {f['slug']}")
        git("pull", "--rebase", "-q")
        git("push", "-q")
    wait_live([PUBLIC + n for n in names])

    user_id = USER_ID or call("me", {"fields": "user_id"})["user_id"]
    children = []
    for n in names:
        c = call(f"{user_id}/media", {"image_url": PUBLIC + n, "is_carousel_item": "true"}, post=True)["id"]
        wait_ready(c)
        children.append(c)
    carousel = call(f"{user_id}/media", {"media_type": "CAROUSEL", "children": ",".join(children), "caption": cap}, post=True)["id"]
    wait_ready(carousel)
    call(f"{user_id}/media_publish", {"creation_id": carousel}, post=True)
    print(f"posted Film of the Week: {f['slug']}")
    state["queue"] = [s for s in state["queue"] if s != f["slug"]]
    state["history"].append({"slug": f["slug"], "date": today.isoformat()})
    save_state(state)


if __name__ == "__main__":
    main()

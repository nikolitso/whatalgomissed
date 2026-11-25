"""Make Instagram posts (1080x1350 image + caption) for films.

Usage: python scripts/instagram_card.py the-hunt father [...]
Writes instagram/<slug>.jpg and instagram/<slug>.txt (the caption, ready to paste).
"""
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from share_on_x import field, slugify  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "brand" / "fonts"
OUT = ROOT / "instagram"
W, H = 1080, 1350
DARK, CREAM, GOLD, MUTED = (14, 13, 11), (245, 242, 237), (212, 173, 74), (168, 157, 140)
DIM = tuple(round(DARK[i] + (236, 228, 212)[i] * .35 - DARK[i] * .35) for i in range(3))
NATIONAL = {"denmark": "danish", "italy": "italian", "france": "french", "iceland": "icelandic", "germany": "german",
            "sweden": "swedish", "norway": "norwegian", "finland": "finnish", "greece": "greek", "spain": "spanish",
            "turkey": "turkish", "brazil": "brazilian", "iran": "iranian", "belgium": "belgian", "poland": "polish",
            "slovakia": "slovak", "japan": "japanese", "southkorea": "korean", "mexico": "mexican", "argentina": "argentine",
            "romania": "romanian", "austria": "austrian", "portugal": "portuguese", "netherlands": "dutch",
            "unitedkingdom": "british", "ireland": "irish", "china": "chinese", "india": "indian", "lebanon": "lebanese",
            "tunisia": "tunisian", "morocco": "moroccan", "israel": "israeli", "hungary": "hungarian", "czechrepublic": "czech"}
GRID = [(18, 18), (32, 18), (46, 18), (18, 32), (32, 32), (46, 32), (18, 46), (32, 46)]


def font(name, size, weight=None):
    f = ImageFont.truetype(str(FONTS / name), size)
    if weight:
        f.set_variation_by_axes([weight])
    return f


def mark(d, x, y, size):
    u = size / 64
    for cx, cy in GRID:
        d.ellipse([x + (cx - 4) * u, y + (cy - 4) * u, x + (cx + 4) * u, y + (cy + 4) * u], fill=DIM)
    d.ellipse([x + 43.5 * u, y + 43.5 * u, x + 54.5 * u, y + 54.5 * u], fill=GOLD)


def wrap(d, text, f, width):
    lines, line = [], ""
    for w in text.split():
        t = f"{line} {w}".strip()
        if d.textlength(t, font=f) <= width:
            line = t
        else:
            lines.append(line)
            line = w
    return lines + [line]


def star_points(cx, cy, r):
    import math
    return [(cx + (r if i % 2 == 0 else r * .42) * math.sin(i * math.pi / 5),
             cy - (r if i % 2 == 0 else r * .42) * math.cos(i * math.pi / 5)) for i in range(10)]


def draw_stars(img, x, y, rating, r):
    """Gold stars drawn as shapes (half stars clipped), so no symbol font is needed."""
    k = 4
    layer = Image.new("RGBA", (round(5 * r * 2.6 * k), round(r * 2.2 * k)), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i in range(5):
        cx, cy = (r + i * r * 2.5) * k, r * 1.1 * k
        d.polygon(star_points(cx, cy, r * k), fill=(*GOLD, 255) if i < rating else (60, 55, 48, 255))
        if 0 < rating - i < 1:  # half star: grey right half
            d.polygon(star_points(cx, cy, r * k), fill=(60, 55, 48, 255))
            half = Image.new("RGBA", layer.size, (0, 0, 0, 0))
            ImageDraw.Draw(half).polygon(star_points(cx, cy, r * k), fill=(*GOLD, 255))
            half = half.crop((0, 0, round(cx), layer.height))
            layer.alpha_composite(half, (0, 0))
    layer = layer.resize((layer.width // k, layer.height // k), Image.LANCZOS)
    img.paste(layer, (x, y - round(r * 1.1)), layer)


def stars(r):
    return "★" * int(r) + ("½" if r % 1 else "")


ISO = {"italy": "IT", "denmark": "DK", "greece": "GR", "israel": "IL", "iceland": "IS", "spain": "ES", "iran": "IR",
       "germany": "DE", "france": "FR", "unitedkingdom": "GB", "sweden": "SE", "norway": "NO", "lebanon": "LB",
       "brazil": "BR", "belgium": "BE", "morocco": "MA", "croatia": "HR", "argentina": "AR", "usa": "US", "turkey": "TR",
       "tunisia": "TN", "mexico": "MX", "ukraine": "UA", "southkorea": "KR", "slovakia": "SK", "serbia": "RS",
       "russia": "RU", "philippines": "PH", "panama": "PA", "netherlands": "NL", "japan": "JP", "india": "IN",
       "hungary": "HU", "georgia": "GE", "czechrepublic": "CZ", "cyprus": "CY", "chile": "CL", "poland": "PL",
       "finland": "FI", "portugal": "PT", "austria": "AT", "romania": "RO", "palestine": "PS", "taiwan": "TW"}

# Closing lines that invite a comment (one per film, picked by slug so it never changes)
QUESTIONS = ["Have you seen it? What did you think of the ending?",
             "Have you seen it? Tell me in the comments.",
             "Seen it already, or is it going on your watchlist?",
             "Which film by this director should I review next?",
             "Did this one ever reach your streaming feed?",
             "Have you seen it? Save this for your next film night."]


def flag(country):
    """Flag emoji for the first country, or '' if unknown."""
    code = ISO.get(re.sub(r"[^a-z]", "", re.split(r"[,/]", country)[0].lower()), "")
    return "".join(chr(0x1F1E6 + ord(c) - 65) for c in code)


def question(slug):
    return QUESTIONS[sum(map(ord, slug)) % len(QUESTIONS)]


def name_tags(title, director):
    """#TheHunt #ThomasVinterberg: hashtags people actually search for the film and director."""
    def tag(s):
        import unicodedata
        s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
        return "#" + "".join(w[:1].upper() + w[1:] for w in re.findall(r"[A-Za-z0-9]+", s))
    names = [d.strip() for d in re.split(r",| and | & ", director) if d.strip()][:2]
    if len(names) == 2 and " " not in names[0]:  # "Jean-Pierre & Luc Dardenne": share the surname
        names[0] += " " + names[1].split()[-1]
    tags = [tag(title)] + [tag(d) for d in names]
    return " ".join(t for t in tags if len(t) > 2)


def card(slug, out=None):
    fm = (ROOT / "content" / "films" / f"{slug}.md").read_text(encoding="utf-8").replace("\r\n", "\n").split("\n---", 1)[0]
    title, year, director = field(fm, "title"), field(fm, "year"), field(fm, "director")
    country, rating = field(fm, "country"), float(field(fm, "rating") or 0)

    img = Image.new("RGB", (W, H), DARK)
    still = Image.open(ROOT / "assets" / "backdrops" / f"{slug}.jpg").convert("RGB")
    ph = 900  # photo area at the top
    s = max(W / still.width, ph / still.height)
    still = still.resize((round(still.width * s), round(still.height * s)), Image.LANCZOS)
    left, top = (still.width - W) // 2, (still.height - ph) // 2
    img.paste(still.crop((left, top, left + W, top + ph)), (0, 0))
    fade = Image.new("L", (1, 260))
    for i in range(260):
        fade.putpixel((0, i), round(255 * (i / 259) ** 1.6))
    img.paste(Image.new("RGB", (W, 260), DARK), (0, ph - 260), fade.resize((W, 260)))

    d = ImageDraw.Draw(img)
    mono = font("IBMPlexMono-Medium.ttf", 26)
    d.text((72, 880), f"{country.upper()} · {year}", font=mono, fill=GOLD)
    size = 92
    while True:
        tf = font("PlayfairDisplay[wght].ttf", size, 700)
        lines = wrap(d, title, tf, W - 144)
        if len(lines) <= 2 or size <= 60:
            break
        size -= 6
    y = 935
    for ln in lines:
        d.text((72, y), ln, font=tf, fill=CREAM)
        y += round(size * 1.12)
    d.text((72, y + 16), f"Directed by {director}", font=font("PlayfairDisplay-Italic[wght].ttf", 36, 400), fill=MUTED)
    draw_stars(img, 72, y + 110, rating, 20)

    d.line([(72, H - 110), (W - 72, H - 110)], fill=(42, 39, 34), width=2)
    mark(d, 66, H - 92, 56)
    brand = font("PlayfairDisplay[wght].ttf", 30, 700)
    base = H - 54
    d.text((132, base), "What Algo ", font=brand, fill=CREAM, anchor="ls")
    d.text((132 + d.textlength("What Algo ", font=brand), base), "Missed", font=font("PlayfairDisplay-Italic[wght].ttf", 30, 400), fill=GOLD, anchor="ls")
    d.text((W - 72, base), "whatalgomissed.com", font=font("IBMPlexMono-Medium.ttf", 22), fill=MUTED, anchor="rs")

    out = Path(out) if out else OUT
    out.mkdir(parents=True, exist_ok=True)
    img.save(out / f"{slug}.jpg", quality=90)

    summary = field(fm, "x_post")
    web = f"whatalgomissed.com/films/{slugify(field(fm, 'slug') or slug)}/"
    tag =re.sub(r"[^a-z]", "", country.lower().split(",")[0])
    tag = NATIONAL.get(tag, tag)
    caption = (f"{summary}\n\n{title} ({year}) {flag(country)}\nDirected by {director} · {country}\nMy rating: {stars(rating)} ({rating:g}/5)\n\n"
               f"{question(slug)}\n\nFull review and trailer: link in bio\n{web}\n\n"
               f"{name_tags(title, director)} #worldcinema #filmrecommendations #cinephile #arthousefilm #{tag}cinema")
    if out == OUT:
        (out / f"{slug}.txt").write_text(caption + "\n", encoding="utf-8")
    print(f"{slug}: ok")
    return caption


if __name__ == "__main__":
    for s in sys.argv[1:]:
        card(s)

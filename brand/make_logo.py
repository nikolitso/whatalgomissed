"""Render the 'missed dot' logo in every size the site and social accounts need."""
import os
from PIL import Image, ImageDraw, ImageFont

S = os.path.dirname(os.path.abspath(__file__))
OUT = r"C:\Users\antonis\Desktop\whatalgomissed\assets"
PREV = os.path.join(S, "logo")
DARK, TILE, CREAM, GOLD, PAPER = (14, 13, 11), (26, 24, 20), (236, 228, 212), (212, 173, 74), (245, 242, 237)
GRID = [(18, 18), (32, 18), (46, 18), (18, 32), (32, 32), (46, 32), (18, 46), (32, 46)]
DIM = tuple(round(DARK[i] + (CREAM[i] - DARK[i]) * .35) for i in range(3))  # cream at 35% on dark


def mark(draw, x, y, size, bg=DARK, radius=True, dim=DIM, pad=0):
    """Draw the 64-unit mark into a size×size box at (x, y). pad shrinks the dots toward the centre."""
    u = size / 64
    if bg:
        if radius:
            draw.rounded_rectangle([x, y, x + size, y + size], radius=10 * u, fill=bg)
        else:
            draw.rectangle([x, y, x + size, y + size], fill=bg)
    k = 1 - pad
    def pt(cx, cy):
        return x + (32 + (cx - 32) * k) * u, y + (32 + (cy - 32) * k) * u
    for cx, cy in GRID:
        px, py = pt(cx, cy); r = 4 * k * u
        draw.ellipse([px - r, py - r, px + r, py + r], fill=dim)
    px, py = pt(49, 49); r = 5.5 * k * u
    draw.ellipse([px - r, py - r, px + r, py + r], fill=GOLD)


def font(italic, weight, size):
    f = ImageFont.truetype(os.path.join(S, "PlayfairDisplay-Italic[wght].ttf" if italic else "PlayfairDisplay[wght].ttf"), size)
    f.set_variation_by_axes([weight])
    return f


def supersample(w, h, paint, scale=4):
    big = Image.new("RGB", (w * scale, h * scale), DARK)
    paint(ImageDraw.Draw(big), scale)
    return big.resize((w, h), Image.LANCZOS)


def wordmark(d, x, y, size, s):
    a = font(False, 700, size * s); b = font(True, 400, size * s)
    d.text((x * s, y * s), "What Algo ", font=a, fill=PAPER)
    w = d.textlength("What Algo ", font=a)
    d.text((x * s + w, y * s), "Missed", font=b, fill=GOLD)
    return w + d.textlength("Missed", font=b)


os.makedirs(PREV, exist_ok=True)

# square icons (rounded tile, for favicons / touch icons / schema logo)
for n, name in [(180, "apple-touch-icon.png"), (512, "logo-512.png"), (32, "favicon-32.png")]:
    img = Image.new("RGBA", (n * 4, n * 4), (0, 0, 0, 0))
    mark(ImageDraw.Draw(img), 0, 0, n * 4, radius=name != "apple-touch-icon.png")
    img.resize((n, n), Image.LANCZOS).save(os.path.join(OUT, name))

# social avatar: full square (platforms crop to a circle), dots pulled in so nothing is clipped
av = supersample(1000, 1000, lambda d, s: mark(d, 0, 0, 1000 * s, radius=False, pad=.12))
av.save(os.path.join(PREV, "avatar-1000.png"))

# Bluesky banner 3000×1000: mark + wordmark, centred
def banner(d, s):
    m = 300; total = m + 80 + 1450
    x0 = (3000 - total) / 2
    mark(d, x0 * s, 350 * s, m * s, bg=TILE)
    wordmark(d, x0 + m + 80, 370, 170, s)
    sub = ImageFont.truetype(os.path.join(S, "IBMPlexMono-Medium.ttf"), 46 * s)
    d.text(((x0 + m + 80) * s, 610 * s), "WORLD CINEMA THE ALGORITHM MISSED", font=sub, fill=(168, 157, 140))
supersample(3000, 1000, banner, scale=2).save(os.path.join(PREV, "banner-3000x1000.png"))

# default share image 1200×630
def og(d, s):
    m = 150
    mark(d, 90 * s, 240 * s, m * s, bg=TILE)
    wordmark(d, 90 + m + 50, 245, 84, s)
    sub = ImageFont.truetype(os.path.join(S, "IBMPlexMono-Medium.ttf"), 24 * s)
    d.text(((90 + m + 50) * s, 365 * s), "A PERSONAL MAP OF WORLD CINEMA", font=sub, fill=(168, 157, 140))
supersample(1200, 630, og).convert("RGB").save(os.path.join(OUT, "og.jpg"), quality=90)

# favicon.svg (crisp at every size)
dots = "".join(f'<circle cx="{x}" cy="{y}" r="4"/>' for x, y in GRID)
svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="10" fill="#0e0d0b"/>'
       f'<g fill="#ece4d4" opacity=".35">{dots}</g><circle cx="49" cy="49" r="5.5" fill="#d4ad4a"/></svg>\n')
open(os.path.join(OUT, "favicon.svg"), "w", encoding="utf-8").write(svg)
open(os.path.join(OUT, "logo-mark.svg"), "w", encoding="utf-8").write(svg)
print("done")

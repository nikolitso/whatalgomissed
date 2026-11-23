"""Make a short vertical Reel (1080x1920 MP4) for a film from 4 stills.

Usage: python scripts/instagram_reel.py the-hunt still1.jpg still2.jpg still3.jpg still4.jpg [--out file.mp4]

Shots: three stills carry the film's summary (x_post) as big captions, the fourth carries
title / director / country / rating, then an end card sends people to the review.
Each still pans slowly and zooms; shots cross-fade. A silent audio track is included
(Instagram's music library can only be added in the app).
"""
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from instagram_card import CREAM, DARK, GOLD, MUTED, draw_stars, font, mark, wrap  # noqa: E402
from share_on_x import field, slugify  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
W, H, FPS = 1080, 1920, 30
SHOT, FADE, END = 3.4, 0.45, 3.0  # seconds per still, cross-fade, end card


def ffmpeg_exe():
    if os.environ.get("FFMPEG"):
        return os.environ["FFMPEG"]
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"


def ease(t):
    return t * t * (3 - 2 * t)


def prepare(path):
    """Scale a landscape still so its height covers the frame with room to zoom."""
    im = Image.open(path).convert("RGB")
    s = H * 1.12 / im.height
    return im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)


def shot_frame(big, t):
    """t in 0..1: pan across the middle of the still while zooming in slightly."""
    zoom = 1.0 + 0.06 * t
    cw, ch = W / zoom * (big.height / (H * 1.12)) * 1.12, H / zoom * (big.height / (H * 1.12)) * 1.12
    cw, ch = min(cw, big.width), min(ch, big.height)
    span = big.width - cw
    cx = span * (0.22 + 0.56 * ease(t))  # sweep across the scene so people at either side are seen
    cy = (big.height - ch) / 2
    return big.crop((round(cx), round(cy), round(cx + cw), round(cy + ch))).resize((W, H), Image.BILINEAR)


def shade(img, strength=1.0):
    """Darken the lower part so captions read on any still."""
    g = Image.new("L", (1, H))
    for y in range(H):
        v = max(0.0, (y - H * 0.42) / (H * 0.58))
        g.putpixel((0, y), round(235 * strength * v ** 1.3))
    img.paste(Image.new("RGB", (W, H), DARK), (0, 0), g.resize((W, H)))
    return img


def caption_layer(lines, kicker=None):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    size = 74
    f = font("PlayfairDisplay[wght].ttf", size, 700)
    rows = [r for ln in lines for r in wrap(d, ln, f, W - 160)]
    while len(rows) > 5 and size > 54:
        size -= 6
        f = font("PlayfairDisplay[wght].ttf", size, 700)
        rows = [r for ln in lines for r in wrap(d, ln, f, W - 160)]
    y = H - 300 - len(rows) * round(size * 1.18)
    if kicker:
        d.text((80, y - 70), kicker, font=font("IBMPlexMono-Medium.ttf", 30), fill=GOLD)
    for r in rows:
        d.text((80, y), r, font=f, fill=CREAM)
        y += round(size * 1.18)
    return layer


def title_layer(fm):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    title, year, director, country = field(fm, "title"), field(fm, "year"), field(fm, "director"), field(fm, "country")
    size = 120
    while True:
        tf = font("PlayfairDisplay[wght].ttf", size, 800)
        rows = wrap(d, title, tf, W - 160)
        if len(rows) <= 2 or size <= 72:
            break
        size -= 8
    y = H - 560 - (len(rows) - 1) * round(size * 1.08)
    d.text((80, y - 64), f"{country.upper()} · {year}", font=font("IBMPlexMono-Medium.ttf", 32), fill=GOLD)
    for r in rows:
        d.text((80, y), r, font=tf, fill=CREAM)
        y += round(size * 1.08)
    d.text((80, y + 24), f"Directed by {director}", font=font("PlayfairDisplay-Italic[wght].ttf", 46, 400), fill=MUTED)
    layer_rgb = Image.new("RGB", (W, H))
    layer_rgb.paste(layer, (0, 0), layer)
    stars = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_stars(stars, 80, y + 130, float(field(fm, "rating") or 0), 30)
    layer.alpha_composite(stars)
    return layer


def end_card(fm, slug):
    img = Image.new("RGB", (W, H), DARK)
    d = ImageDraw.Draw(img)
    mark(d, W // 2 - 70, 560, 140)
    brand = font("PlayfairDisplay[wght].ttf", 64, 700)
    ital = font("PlayfairDisplay-Italic[wght].ttf", 64, 400)
    w1, w2 = d.textlength("What Algo ", font=brand), d.textlength("Missed", font=ital)
    x = (W - w1 - w2) / 2
    d.text((x, 780), "What Algo ", font=brand, fill=CREAM)
    d.text((x + w1, 780), "Missed", font=ital, fill=GOLD)
    d.text((W // 2, 930), "WORLD CINEMA THE ALGORITHM MISSED", font=font("IBMPlexMono-Medium.ttf", 28), fill=MUTED, anchor="mm")
    d.line([(W // 2 - 60, 1030), (W // 2 + 60, 1030)], fill=GOLD, width=2)
    d.text((W // 2, 1130), "Full review + trailer", font=font("PlayfairDisplay[wght].ttf", 58, 700), fill=CREAM, anchor="mm")
    d.text((W // 2, 1215), "link in bio", font=font("PlayfairDisplay-Italic[wght].ttf", 52, 400), fill=GOLD, anchor="mm")
    url = f"whatalgomissed.com/films/{slugify(field(fm, 'slug') or slug)}"
    d.text((W // 2, 1330), url, font=font("IBMPlexMono-Medium.ttf", 30), fill=MUTED, anchor="mm")
    return img


MUSIC = ROOT / "brand" / "music"
# film country -> music folder (brand/music/<folder>/)
REGIONS = {
    "italy": "italy",
    "denmark": "nordic", "iceland": "nordic", "sweden": "nordic", "norway": "nordic", "finland": "nordic",
    "greece": "greece", "cyprus": "greece",
    "israel": "middle-east", "iran": "middle-east", "palestine": "middle-east", "lebanon": "middle-east",
    "turkey": "middle-east", "tunisia": "middle-east", "morocco": "middle-east", "egypt": "middle-east",
    "spain": "latin", "argentina": "latin", "brazil": "latin", "mexico": "latin", "chile": "latin",
    "panama": "latin", "colombia": "latin",
    "france": "france", "belgium": "france", "netherlands": "france",
    "japan": "asia", "south-korea": "asia", "taiwan": "asia", "philippines": "asia", "india": "asia", "china": "asia",
}


def music_for(country):
    """Tracks for the film's first country's region, else the general folder."""
    first = slugify(re.split(r"[,/]", country or "")[0].strip())
    audio = (".mp3", ".m4a", ".wav")
    for folder in (REGIONS.get(first, "europe"), "general"):
        tracks = sorted(p for p in (MUSIC / folder).glob("*") if p.suffix.lower() in audio)
        if tracks:
            return tracks
    return sorted(p for p in MUSIC.glob("*") if p.suffix.lower() in audio)


def summary_parts(fm):
    """Split the summary into three short captions."""
    text = field(fm, "x_post") or field(fm, "logline")
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    parts = []
    for s in sents:  # long sentences split at their turn ("…, and …") so each caption stays short
        if ", and " in s and len(s) > 60:
            a, b = s.split(", and ", 1)
            parts += [a + "…", "…and " + b]
        else:
            parts.append(s)
    return (parts + ["", "", ""])[:3]


def reel(slug, stills, out):
    fm = (ROOT / "content" / "films" / f"{slug}.md").read_text(encoding="utf-8").replace("\r\n", "\n").split("\n---", 1)[0]
    parts = summary_parts(fm)
    if len(parts) == 3 and parts[0].endswith("…"):
        pass
    bigs = [prepare(p) for p in stills[:4]]
    layers = [caption_layer([parts[0]], "A FILM THE ALGORITHM MISSED"),
              caption_layer([parts[1]]), caption_layer([parts[2]]), title_layer(fm)]
    endimg = end_card(fm, slug)

    total = 4 * SHOT + END
    n = round(total * FPS)
    # Music: royalty-free tracks in brand/music/<region>/ matching the film's country,
    # falling back to brand/music/general/; silent if nothing is there.
    tracks = music_for(field(fm, "country"))
    if tracks:
        track = tracks[int(hashlib.sha1(slug.encode()).hexdigest(), 16) % len(tracks)]
        audio_in = ["-stream_loop", "-1", "-i", str(track)]
        audio_fx = ["-af", f"afade=t=in:d=0.8,afade=t=out:st={total - 1.8:.2f}:d=1.8,volume=0.85"]
        print("music:", track.name)
    else:
        audio_in, audio_fx = ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"], []
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", *audio_in, "-map", "0:v", "-map", "1:a", *audio_fx,
           "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    def scene(i, t_abs):
        """Frame of shot i at absolute time t_abs (seconds since the shot started)."""
        t = min(max(t_abs / (SHOT + FADE), 0), 1)
        img = shade(shot_frame(bigs[i], t), 1.0 if i < 3 else 1.15)
        a = min(max((t_abs - 0.25) / 0.35, 0), 1)  # caption fades in just after the cut
        if a > 0:
            lay = layers[i].copy()
            if a < 1:
                lay.putalpha(lay.getchannel("A").point(lambda v: round(v * a)))
            img.paste(lay, (0, 0), lay)
        return img

    for k in range(n):
        ts = k / FPS
        i = int(ts // SHOT)
        if i < 4:
            frame = scene(i, ts - i * SHOT)
            into_next = ts - (i + 1) * SHOT + FADE
            if into_next > 0:  # cross-fade into the next shot (or the end card)
                nxt = scene(i + 1, into_next - FADE) if i < 3 else endimg
                frame = Image.blend(frame, nxt, ease(min(into_next / FADE, 1)))
        else:
            frame = endimg
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    if proc.wait():
        raise SystemExit("ffmpeg failed")
    print(f"{slug}: {out} ({total:.1f}s)")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--out")]
    out = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--out=")), None)
    slug, stills = args[0], args[1:]
    out = Path(out or ROOT / "instagram" / f"{slug}-reel.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    reel(slug, stills, out)

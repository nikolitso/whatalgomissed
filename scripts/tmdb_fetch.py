"""Fetch a high-resolution backdrop and a poster for every film from TMDB.

Run locally:  python scripts/tmdb_fetch.py          (only films not fetched yet)
              python scripts/tmdb_fetch.py --all    (refetch everything)
              python scripts/tmdb_fetch.py SLUG     (one film; add "id=12345" to force a TMDB id)
              python scripts/tmdb_fetch.py --cast   (only fill in missing actors for already-matched films)

Reads the TMDB API Read Access Token from tmdb_key.txt (git-ignored) or the TMDB_TOKEN env var.
To choose a specific still, set "pin": "/<tmdb file path>.jpg" for the film in content/tmdb.json and rerun.
Writes assets/backdrops/<slug>.jpg (1280px), assets/posters/<slug>.jpg (500px) and content/tmdb.json,
and adds the top 3 billed actors as "actors:" to a film's front matter when it has none (never overwrites edits).
This product uses the TMDB API but is not endorsed or certified by TMDB.
"""
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILMS = ROOT / "content" / "films"
OUT_JSON = ROOT / "content" / "tmdb.json"
BACKDROPS = ROOT / "assets" / "backdrops"
POSTERS = ROOT / "assets" / "posters"
API = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p"


def token():
    t = os.environ.get("TMDB_TOKEN") or (ROOT / "tmdb_key.txt").read_text(encoding="utf-8").strip()
    if not t:
        sys.exit("No TMDB token found")
    return t


TOKEN = token()


def get(path, **params):
    url = f"{API}{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}", "accept": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2 + attempt * 2)
                continue
            if e.code == 401:
                sys.exit("TMDB rejected the token (401). Check tmdb_key.txt holds the API Read Access Token.")
            raise
    raise RuntimeError(f"TMDB kept rate-limiting {path}")


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (whatalgomissed build)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


def front(path):
    s = path.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---", s.replace("\r\n", "\n"), re.S)
    meta = {}
    for line in m.group(1).split("\n"):
        mm = re.match(r'^([a-z_]+):\s*"?(.*?)"?\s*$', line)
        if mm and mm.group(2):
            meta[mm.group(1)] = mm.group(2)
    return meta


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z ]", " ", s).split()


def director_matches(ours, crew):
    """Lenient but safe: surnames compared with spaces/hyphens removed, or a shared long name part."""
    ours_names = [norm(x) for x in re.split(r",|&| and ", ours or "") if x.strip()]
    theirs = [norm(c["name"]) for c in crew if c.get("job") == "Director"]
    for o in ours_names:
        for t in theirs:
            if not o or not t:
                continue
            oj, tj = "".join(o), "".join(t)
            if o[-1] == t[-1] or o[-1] in tj or t[-1] in oj or any(len(w) >= 4 and w in t for w in o):
                return True
    return False


def top_cast(credits, n=3):
    cast = sorted(credits.get("cast", []), key=lambda c: c.get("order", 999))
    return [c["name"] for c in cast[:n]]


def write_actors(path, names):
    """Insert an actors: list after director: (or year:) unless the film already has one."""
    if not names:
        return False
    raw = path.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    s = raw.replace("\r\n", "\n")
    head, sep, rest = s[4:].partition("\n---")
    if re.search(r"^actors:", head, re.M):
        return False
    block = "actors:\n" + "".join(f'  - "{n.replace(chr(34), chr(39))}"\n' for n in names)
    anchor = re.search(r"^director:.*\n", head, re.M) or re.search(r"^year:.*\n", head, re.M)
    head = head[:anchor.end()] + block + head[anchor.end():] if anchor else head + "\n" + block.rstrip("\n")
    path.write_bytes(("---\n" + head + sep + rest).replace("\n", nl).encode("utf-8"))
    return True


def candidates(meta):
    seen = []
    year = int(meta.get("year", 0) or 0)
    for q in filter(None, [meta.get("title"), meta.get("original_title")]):
        for y in (year, year - 1, year + 1, None):
            params = {"query": q, "include_adult": "false"}
            if y:
                params["primary_release_year"] = y
            for r in get("/search/movie", **params).get("results", [])[:10]:
                if r["id"] not in seen:
                    seen.append(r["id"])
            if seen and y == year:
                break
    return seen


def backdrop_order(images, fallback):
    bd = images.get("backdrops", [])
    # textless first (no language), then by votes, then by size
    bd.sort(key=lambda b: (b.get("iso_639_1") is not None, -b.get("vote_average", 0), -b.get("width", 0)))
    paths = [b["file_path"] for b in bd]
    return paths or ([fallback] if fallback else [])


def looks_like_promo_art(path):
    """Key art on a white background (title text, cut-out cast) rather than a film still."""
    from PIL import Image, ImageStat
    im = Image.open(path).convert("L")
    w, h = im.size
    edges = [im.crop((0, 0, w, int(h * .06))), im.crop((0, int(h * .94), w, h)),
             im.crop((0, 0, int(w * .05), h)), im.crop((int(w * .95), 0, w, h))]
    return sum(ImageStat.Stat(e).mean[0] > 225 for e in edges) >= 2


def save_backdrop(paths, dest):
    """Download candidates in order and keep the first that is a real still (else the first one)."""
    first = None
    for fp in paths[:8]:
        download(f"{IMG}/w1280{fp}", dest)
        if first is None:
            first = dest.read_bytes()
        if not looks_like_promo_art(dest):
            return True
    if first is not None:
        dest.write_bytes(first)
        return True
    return False


def fetch(slug, meta, force_id=None, pin=None):
    ids = [force_id] if force_id else candidates(meta)
    for mid in ids:
        d = get(f"/movie/{mid}", append_to_response="credits,images", include_image_language="en,null")
        if force_id or director_matches(meta.get("director"), d.get("credits", {}).get("crew", [])):
            paths = backdrop_order(d.get("images", {}), d.get("backdrop_path"))
            if pin:
                paths = [pin]
            poster = d.get("poster_path")
            rec = {"id": d["id"], "title": d.get("title"), "year": (d.get("release_date") or "")[:4],
                   "cast": top_cast(d.get("credits", {}))}
            if paths and save_backdrop(paths, BACKDROPS / f"{slug}.jpg"):
                rec["backdrop"] = f"/assets/backdrops/{slug}.jpg"
            if poster:
                download(f"{IMG}/w500{poster}", POSTERS / f"{slug}.jpg")
                rec["poster"] = f"/assets/posters/{slug}.jpg"
            if pin:
                rec["pin"] = pin
            return rec
    return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force_id = next((int(a[3:]) for a in args if a.startswith("id=")), None)
    only = [a for a in args if not a.startswith("id=")]
    data = json.loads(OUT_JSON.read_text(encoding="utf-8")) if OUT_JSON.exists() else {}
    files = sorted(FILMS.glob("*.md"))
    if "--cast" in sys.argv:
        added = 0
        for p in files:
            rec = data.get(p.stem)
            if not rec or re.search(r"^actors:", p.read_text(encoding="utf-8"), re.M):
                continue
            rec["cast"] = top_cast(get(f"/movie/{rec['id']}/credits"))
            if write_actors(p, rec["cast"]):
                added += 1
                print(f"{p.stem}: {', '.join(rec['cast'])}")
            time.sleep(0.05)
        OUT_JSON.write_text(json.dumps(dict(sorted(data.items())), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nDone. Added actors to {added} films.")
        return
    if only:
        files = [f for f in files if f.stem in only]
    elif "--all" not in sys.argv:
        files = [f for f in files if f.stem not in data or data[f.stem] is None]
    missing = []
    for i, p in enumerate(files, 1):
        meta = front(p)
        try:
            rec = fetch(p.stem, meta, force_id, (data.get(p.stem) or {}).get("pin"))
        except Exception as e:
            rec = None
            print(f"  error {p.stem}: {e}")
        data[p.stem] = rec
        if rec:
            write_actors(p, rec.get("cast"))
        if not rec:
            missing.append(f"{p.stem} ({meta.get('title')}, {meta.get('year')}, {meta.get('director')})")
        print(f"[{i}/{len(files)}] {p.stem}: " + (f"TMDB {rec['id']} {rec['title']} ({rec['year']})" if rec else "NOT MATCHED"))
        time.sleep(0.05)
    OUT_JSON.write_text(json.dumps(dict(sorted(data.items())), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nDone. Matched {sum(1 for v in data.values() if v)} of {len(data)}.")
    if missing:
        print("Not matched:\n  " + "\n  ".join(missing))


if __name__ == "__main__":
    main()

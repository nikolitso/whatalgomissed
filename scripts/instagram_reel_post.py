"""Post one film a day as an Instagram Reel.

Usage (in the Action):  python scripts/instagram_reel_post.py [--dry-run] [--force]

Picks the next film (best rated first, mixed order), fetches 4 text-free stills from TMDB,
renders a ~17s Reel with instagram_reel.py and uploads the video straight to Instagram
(resumable upload, so nothing is hosted on the site). Posted films are recorded in
content/instagram_reels_posted.json. Needs INSTAGRAM_TOKEN, INSTAGRAM_USER_ID and TMDB_TOKEN.
"""
import hashlib
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bluesky_post import film  # noqa: E402
from instagram_card import NATIONAL, stars  # noqa: E402
from instagram_post import API, TOKEN, USER_ID, call  # noqa: E402
from instagram_reel import reel  # noqa: E402
from share_on_x import field, slugify  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FILMS = ROOT / "content" / "films"
STATE = ROOT / "content" / "instagram_reels_posted.json"
TMDB = json.loads((ROOT / "content" / "tmdb.json").read_text(encoding="utf-8"))
MIN_GAP_HOURS = 18  # backup schedule slots skip if a Reel already went out today


def load_state():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else []


def save_state(posted):
    STATE.write_text(json.dumps(list(dict.fromkeys(posted)), indent=1) + "\n", encoding="utf-8")


def tmdb(path):
    req = urllib.request.Request("https://api.themoviedb.org/3/" + path,
                                 headers={"Authorization": "Bearer " + os.environ["TMDB_TOKEN"].strip()})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def stills_for(slug, folder):
    """Download up to 4 stills without title text (TMDB marks those with no language)."""
    tid = (TMDB.get(slug) or {}).get("id")
    if not tid:
        return []
    backs = tmdb(f"movie/{tid}/images?include_image_language=null")["backdrops"]
    paths = [b["file_path"] for b in backs if b.get("iso_639_1") is None and b.get("width", 0) >= 1280][:4]
    files = []
    for i, p in enumerate(paths):
        f = Path(folder) / f"{i}.jpg"
        with urllib.request.urlopen("https://image.tmdb.org/t/p/w1280" + p, timeout=60) as r:
            f.write_bytes(r.read())
        files.append(str(f))
    return files


def caption(f):
    fm = f["fm"]
    title, year, director, country = field(fm, "title"), field(fm, "year"), field(fm, "director"), field(fm, "country")
    rating = float(field(fm, "rating") or 0)
    tag = NATIONAL.get(slugify(country.split(",")[0]).replace("-", ""), slugify(country.split(",")[0]).replace("-", ""))
    web = f"whatalgomissed.com/films/{f['slug']}/"
    return (f"{field(fm, 'x_post')}\n\n{title} ({year})\nDirected by {director} · {country}\n"
            f"My rating: {stars(rating)} ({rating:g}/5)\n\nFull review and trailer: link in bio\n{web}\n\n"
            f"#worldcinema #filmrecommendations #cinephile #arthousefilm #{tag}cinema #moviereels")


def hours_since_last_reel(user_id):
    media = call(f"{user_id}/media", {"fields": "timestamp,media_product_type", "limit": 25}).get("data", [])
    reels = [m for m in media if m.get("media_product_type") == "REELS"]
    if not reels:
        return None
    last = datetime.strptime(reels[0]["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
    return (datetime.now(timezone.utc) - last).total_seconds() / 3600


def upload_reel(user_id, video, cap):
    """Resumable upload: create the container, send the bytes, wait for processing, publish."""
    created = call(f"{user_id}/media", {"media_type": "REELS", "upload_type": "resumable",
                                        "caption": cap, "share_to_feed": "true"}, post=True)
    data = Path(video).read_bytes()
    req = urllib.request.Request(created["uri"], data=data, method="POST", headers={
        "Authorization": "OAuth " + TOKEN, "offset": "0", "file_size": str(len(data))})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            r.read()
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Reel upload failed: {e.read().decode(errors='replace')[:400]}")
    for _ in range(60):  # video processing usually takes under a minute
        status = call(created["id"], {"fields": "status_code"}).get("status_code")
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED"):
            raise SystemExit(f"Instagram could not process the Reel ({status})")
        time.sleep(10)
    else:
        raise SystemExit("Reel still processing after 10 minutes")
    call(f"{user_id}/media_publish", {"creation_id": created["id"]}, post=True)


def main():
    dry, force = "--dry-run" in sys.argv, "--force" in sys.argv
    posted = load_state()
    films = [film(p) for p in sorted(FILMS.glob("*.md"))]
    backlog = [f for f in films if f["share"] and f["slug"] not in posted]
    backlog.sort(key=lambda f: (-(f["rating"] >= 4.5), -f["rating"], hashlib.sha1(f["slug"].encode()).hexdigest()))

    user_id = None
    if not dry:
        user_id = USER_ID or call("me", {"fields": "user_id"})["user_id"]
        if not force:
            gap = hours_since_last_reel(user_id)
            if gap is not None and gap < MIN_GAP_HOURS:
                print(f"last Reel was {gap:.1f}h ago; this slot already ran")
                return

    with tempfile.TemporaryDirectory() as tmp:
        for f in backlog:  # first film with at least 3 usable stills
            files = stills_for(f["slug"], tmp)
            if len(files) >= 3:
                break
            print(f"skipping {f['slug']}: only {len(files)} text-free stills on TMDB")
        else:
            print("nothing to post")
            return
        while len(files) < 4:  # 3 stills: reuse the first for the title shot
            files.append(files[0])
        out = Path(tmp) / f"{f['slug']}.mp4"
        reel(f["slug"], files, out)
        cap = caption(f)
        print(f"--- {f['slug']}\n{cap}\n")
        if dry:
            keep = ROOT / "instagram" / f"{f['slug']}-reel.mp4"
            keep.parent.mkdir(exist_ok=True)
            keep.write_bytes(out.read_bytes())
            print("dry run: saved", keep)
            return
        upload_reel(user_id, out, cap)
    print(f"posted Reel: {f['slug']}")
    posted.append(f["slug"])
    save_state(posted)


if __name__ == "__main__":
    main()

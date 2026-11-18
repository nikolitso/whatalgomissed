"""Post films to Bluesky with a link card (image, title, summary).

Usage (in the Action):
  python scripts/bluesky_post.py new content/films/a.md [...]   post newly added films
  python scripts/bluesky_post.py daily                           post the next film from the backlog
Add --dry-run to print instead of posting.

Needs BLUESKY_HANDLE and BLUESKY_APP_PASSWORD (a Bluesky app password, stored as a GitHub secret).
Films with `share: false` are never posted. Posted films are recorded in content/bluesky_posted.json,
so nothing is posted twice. The backlog goes Must See first (highest rated), then everything else.
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from share_on_x import SITE, bluesky_post, build_post, field, slugify  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FILMS = ROOT / "content" / "films"
STATE = ROOT / "content" / "bluesky_posted.json"
PDS = "https://bsky.social/xrpc"


def api(method, body=None, token=None, raw=None, ctype="application/json"):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(f"{PDS}/{method}", data=data, method="POST" if data is not None else "GET")
    req.add_header("Content-Type", ctype)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def load_state():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else []


def save_state(posted):
    STATE.write_text(json.dumps(sorted(set(posted)), indent=1) + "\n", encoding="utf-8")


def film(path):
    text = path.read_text(encoding="utf-8")
    fm = text.replace("\r\n", "\n").split("\n---", 1)[0]
    slug = slugify(field(fm, "slug") or path.stem)
    rating = float(field(fm, "rating") or 0)
    return {"path": path, "slug": slug, "text": text, "fm": fm, "rating": rating,
            "title": field(fm, "title"), "share": field(fm, "share").lower() not in ("false", "no"),
            "url": SITE + slug + "/"}


def compose(f):
    post = bluesky_post(build_post(f["fm"], f["text"]), f["url"])
    b = post.encode("utf-8")
    start = b.rfind(f["url"].encode("utf-8"))
    facets = [{"index": {"byteStart": start, "byteEnd": start + len(f["url"].encode("utf-8"))},
               "features": [{"$type": "app.bsky.richtext.facet#link", "uri": f["url"]}]}]
    desc = field(f["fm"], "logline") or field(f["fm"], "x_post")
    return post, facets, desc


def publish(f, session, dry):
    post, facets, desc = compose(f)
    print(f"--- {f['slug']} ({len(post)} chars)\n{post}\n")
    if dry:
        return
    token = session["accessJwt"]
    card = {"uri": f["url"], "title": f"{f['title']} | What Algo Missed", "description": desc[:300]}
    img = ROOT / "assets" / "backdrops" / f"{f['slug']}.jpg"
    if img.exists() and img.stat().st_size < 950_000:
        blob = api("com.atproto.repo.uploadBlob", raw=img.read_bytes(), token=token, ctype="image/jpeg")
        card["thumb"] = blob["blob"]
    record = {"$type": "app.bsky.feed.post", "text": post, "facets": facets, "langs": ["en"],
              "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
              "embed": {"$type": "app.bsky.embed.external", "external": card}}
    api("com.atproto.repo.createRecord", {"repo": session["did"], "collection": "app.bsky.feed.post",
                                           "record": record}, token=token)


def main():
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry = "--dry-run" in sys.argv
    mode, paths = (args[0] if args else "daily"), args[1:]
    posted = load_state()
    if mode == "new":
        todo = [film(Path(p)) for p in paths if Path(p).exists()]
    else:
        films = [film(p) for p in sorted(FILMS.glob("*.md"))]
        backlog = [f for f in films if f["slug"] not in posted]
        backlog.sort(key=lambda f: (-(f["rating"] >= 4.5), -f["rating"], f["title"]))
        todo = backlog[:1]
    todo = [f for f in todo if f["share"] and f["slug"] not in posted]
    if not todo:
        print("nothing to post")
        return
    session = None
    if not dry:
        session = api("com.atproto.server.createSession", {
            "identifier": os.environ["BLUESKY_HANDLE"], "password": os.environ["BLUESKY_APP_PASSWORD"]})
    for f in todo:
        publish(f, session, dry)
        posted.append(f["slug"])
    if not dry:
        save_state(posted)


if __name__ == "__main__":
    main()

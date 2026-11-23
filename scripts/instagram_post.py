"""Post films to Instagram (image + caption) through the Instagram API with Instagram Login.

Usage (in the Action):
  python scripts/instagram_post.py new content/films/a.md [...]   post newly added films
  python scripts/instagram_post.py daily                           post the next film from the backlog
Flags: --dry-run (render and print only), --force (ignore the "posted recently" guard).

Needs INSTAGRAM_TOKEN (a long-lived Instagram user token, stored as a GitHub secret).
Instagram fetches the image from a public URL, so the card is rendered to assets/instagram/<slug>.jpg,
committed and pushed, and the script waits until Cloudflare has published it before posting.
Films with `share: false` are never posted. Posted films are recorded in content/instagram_posted.json.
"""
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bluesky_post import film  # noqa: E402
from instagram_card import card  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FILMS = ROOT / "content" / "films"
STATE = ROOT / "content" / "instagram_posted.json"
IMAGES = ROOT / "assets" / "instagram"
PUBLIC = "https://whatalgomissed.com/assets/instagram/"
TOKEN = os.environ.get("INSTAGRAM_TOKEN", "").strip().strip('"').strip()
# Tokens from "Continue with Instagram" start with IG and use graph.instagram.com;
# Facebook-style tokens (EAA...) from Meta's unified login use graph.facebook.com.
IG_STYLE = TOKEN.startswith("IG")
API = "https://graph.instagram.com/v23.0" if IG_STYLE else "https://graph.facebook.com/v23.0"
USER_ID = os.environ.get("INSTAGRAM_USER_ID", "").strip()
MIN_GAP_HOURS = 20  # backup schedule slots skip if a post went out within this window


def call(path, params=None, post=False, base=API):
    params = dict(params or {}, access_token=TOKEN)
    data = urllib.parse.urlencode(params).encode()
    url = f"{base}/{path}" if post else f"{base}/{path}?{data.decode()}"
    req = urllib.request.Request(url, data=data if post else None, method="POST" if post else "GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:  # show Instagram's error message, never the token
        raise SystemExit(f"Instagram API error on {path}: {e.read().decode(errors='replace')[:500]}")


def load_state():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else []


def save_state(posted):
    # keep posting order (oldest first): the /ig/ page on the site shows newest first
    STATE.write_text(json.dumps(list(dict.fromkeys(posted)), indent=1) + "\n", encoding="utf-8")


def hours_since_last_post(user_id):
    media = call(f"{user_id}/media", {"fields": "timestamp", "limit": 1}).get("data", [])
    if not media:
        return None
    last = datetime.strptime(media[0]["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
    return (datetime.now(timezone.utc) - last).total_seconds() / 3600


def git(*args):
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def publish_images(slugs):
    """Commit the rendered cards and wait until the live site serves them."""
    git("add", *[str(IMAGES / f"{s}.jpg") for s in slugs])
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode:
        git("commit", "-q", "-m", "Instagram: images for " + ", ".join(slugs))
        git("pull", "--rebase", "-q")
        git("push", "-q")
    for s in slugs:
        url = PUBLIC + s + ".jpg"
        # Cloudflare blocks the default Python user agent, so the check names itself.
        for _ in range(60):  # up to 10 minutes for Cloudflare to deploy
            try:
                with urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers={"User-Agent": "whatalgomissed-bot/1.0 (+https://whatalgomissed.com)"}), timeout=20) as r:
                    if r.status == 200 and r.headers.get("Content-Type", "").startswith("image/"):
                        break
            except urllib.error.URLError:
                pass
            time.sleep(10)
        else:
            raise SystemExit(f"{url} never went live; not posting")


def post_one(user_id, slug, caption):
    container = call(f"{user_id}/media", {"image_url": PUBLIC + slug + ".jpg", "caption": caption}, post=True)["id"]
    for _ in range(30):  # Instagram processes the image before it can be published
        status = call(container, {"fields": "status_code"}).get("status_code")
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED"):
            raise SystemExit(f"Instagram could not process the image for {slug} ({status})")
        time.sleep(5)
    call(f"{user_id}/media_publish", {"creation_id": container}, post=True)
    print(f"posted {slug}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry, force = "--dry-run" in sys.argv, "--force" in sys.argv
    count = next((int(a.split("=", 1)[1]) for a in sys.argv if a.startswith("--count=")), 1)
    count = max(1, min(count, 25))  # Instagram allows ~100 API posts a day; stay well under
    mode, paths = (args[0] if args else "daily"), args[1:]
    posted = load_state()

    if mode == "new":
        todo = [film(Path(p)) for p in paths if Path(p).exists()]
    else:
        films = [film(p) for p in sorted(FILMS.glob("*.md"))]
        backlog = [f for f in films if f["slug"] not in posted]
        # best rated first; within a rating, a fixed shuffle (not A-Z) so a batch mixes countries and titles
        backlog.sort(key=lambda f: (-(f["rating"] >= 4.5), -f["rating"], hashlib.md5(f["slug"].encode()).hexdigest()))
        # Post a batch in reverse, so the best film of the batch ends up newest (top of the profile grid)
        todo = list(reversed(backlog[:count]))
    todo = [f for f in todo if f["share"] and f["slug"] not in posted
            and (ROOT / "assets" / "backdrops" / f"{f['slug']}.jpg").exists()]
    if not todo:
        print("nothing to post")
        return

    user_id = None
    if not dry:
        print(f"token type: {'Instagram' if IG_STYLE else 'Facebook'} ({len(TOKEN)} characters)")
        if IG_STYLE:  # refresh keeps a long-lived Instagram token valid for another 60 days
            refreshed = call("refresh_access_token", {"grant_type": "ig_refresh_token"}, base="https://graph.instagram.com")
            print(f"token valid for {refreshed.get('expires_in', 0) // 86400} more days")
        user_id = USER_ID or call("me", {"fields": "user_id,username"})["user_id"]
        print("posting as", call(user_id, {"fields": "username"}).get("username"))
        if mode == "daily" and not force:
            gap = hours_since_last_post(user_id)
            if gap is not None and gap < MIN_GAP_HOURS:
                print(f"last Instagram post was {gap:.1f}h ago; this slot already ran")
                return

    captions = {f["slug"]: card(f["slug"], None if dry else IMAGES) for f in todo}
    if dry:
        for s, c in captions.items():
            print(f"--- {s}\n{c}\n")
        return
    publish_images(list(captions))
    for i, (s, c) in enumerate(captions.items()):
        if i:
            time.sleep(90)  # space out a batch so a new account doesn't look like a spam burst
        post_one(user_id, s, c)
        posted.append(s)
        save_state(posted)


if __name__ == "__main__":
    main()

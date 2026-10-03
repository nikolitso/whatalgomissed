"""For each newly added film, open a GitHub issue (assigned to the owner, so GitHub emails it)
with a one-tap link that opens X with the post already written.

Usage (in the Action): python scripts/share_on_x.py content/films/new-film.md [...]
"""
import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

SITE = "https://whatalgomissed.com/films/"
OWNER = os.environ.get("SHARE_ASSIGNEE", "nikolitso")


def slugify(t):  # same as build.py
    t = str(t).lower()
    t = (t.replace("ά", "α").replace("έ", "ε").replace("ή", "η").replace("ί", "ι")
          .replace("ό", "ο").replace("ύ", "υ").replace("ώ", "ω"))
    t = re.sub(r"[^\w\s-]", "", t, flags=re.U)
    return re.sub(r"[\s_-]+", "-", t).strip("-")


def field(fm, key):
    m = re.search(rf"^{key}:\s*(.*)$", fm, re.M)
    return m.group(1).strip().strip("\"'") if m else ""


def main(paths):
    for p in paths:
        path = Path(p)
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        fm = text.split("\n---", 1)[0]
        title, year, director = field(fm, "title"), field(fm, "year"), field(fm, "director")
        slug = slugify(field(fm, "slug") or path.stem)
        url = SITE + slug + "/"
        post = f"New on What Algo Missed: {title} ({year})" + (f" by {director}" if director else "")
        intent = "https://x.com/intent/post?" + urllib.parse.urlencode({"text": post, "url": url})
        body = (
            f"A new film is live on What Algo Missed: **{title}**\n\n"
            f"### [👉 Post it on X]({intent})\n\n"
            f"Opens X with this post ready (edit anything before posting):\n\n> {post} {url}\n\n"
            f"Page: {url}\n\n_Give the site a minute to publish before posting, so the preview image appears. Close this issue once posted._"
        )
        issue_title = f"Share on X: {title}"
        print(issue_title, "\n", intent)
        if os.environ.get("GITHUB_ACTIONS"):
            subprocess.run(["gh", "issue", "create", "--title", issue_title, "--body", body, "--assignee", OWNER], check=False)


if __name__ == "__main__":
    main(sys.argv[1:])

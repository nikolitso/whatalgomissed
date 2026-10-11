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


X_LIMIT = 280
X_URL_LEN = 23  # X counts every link as 23 characters


def review_sentence(text):
    """Opening sentences of the review, as the fallback summary."""
    body = re.sub(r"\s+", " ", text.split("\n---", 1)[1] if "\n---" in text else text).strip()
    body = re.sub(r"[*_#>]", "", body)
    sentences = re.split(r"(?<=[.!?])\s+", body)
    out = ""
    for s in sentences:
        if len(out) + len(s) + 1 > 200:
            break
        out = (out + " " + s).strip()
    return out or (body[:197].rsplit(" ", 1)[0] + "…")


def build_post(fm, text):
    title, year, director = field(fm, "title"), field(fm, "year"), field(fm, "director")
    summary = field(fm, "x_post") or review_sentence(text)
    credit = f"{title} ({year})" + (f", {director}" if director else "")
    room = X_LIMIT - X_URL_LEN - len(credit) - 4  # two line breaks + space before the link
    if len(summary) > room:
        summary = summary[:room - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return f"{summary}\n\n{credit}"


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
        post = build_post(fm, text)
        intent = "https://x.com/intent/post?" + urllib.parse.urlencode({"text": post, "url": url})
        body = (
            f"A new film is live on What Algo Missed: **{title}**\n\n"
            f"### [👉 Post it on X]({intent})\n\n"
            "Opens X with this post ready (edit anything before posting):\n\n"
            + "\n".join("> " + line for line in f"{post} {url}".split("\n")) + "\n\n"
            f"Page: {url}\n\n_Give the site a minute to publish before posting, so the preview image appears. Close this issue once posted._"
        )
        issue_title = f"Share on X: {title}"
        print(issue_title, "\n", intent)
        if os.environ.get("GITHUB_ACTIONS"):
            subprocess.run(["gh", "issue", "create", "--title", issue_title, "--body", body, "--assignee", OWNER], check=False)


if __name__ == "__main__":
    main(sys.argv[1:])

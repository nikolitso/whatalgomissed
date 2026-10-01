# whatalgomissed.com

The Films the Algorithm Missed — a personal map of world cinema.

## Adding a film
Open **https://app.pagescms.org**, choose this repository → **Films** → **Add entry**.
Fill in title, year, country, rating, lists, paste the YouTube trailer link, write the review, Save.
The site rebuilds itself about a minute later.

## How it works
- `content/films/` — one file per film
- `content/lists/` — the lists and their introductions
- `content/pages/about.md` — About page
- `content/finder.json` — which films the Film Finder can recommend
- `build.py` — turns the content into the website (plain Python, no installs)

Build locally: `python3 build.py` → output in `_site/`.

Hosting: Cloudflare Pages — build command `python3 build.py`, output directory `_site`.

New list? Add it under **Lists** in the editor, then add the same name to the `lists` options in `.pages.yml`.

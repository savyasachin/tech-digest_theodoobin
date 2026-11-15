"""
Fetches fresh Odoo-ecosystem news plus general tech/world headlines from free
RSS/Atom feeds, renders them into a clean, styled HTML page (docs/index.html,
served for free via GitHub Pages), and sends a short teaser push notification
via ntfy.sh pointing at that page - no account, no card, no phone-number
linking, and a real custom UI instead of a wall of text in the notification.

Required environment variables (set as GitHub Actions secrets):
  NTFY_TOPIC     - your private topic name, e.g. yourname-odoo-digest-7f3k2
  PAGES_URL      - the GitHub Pages URL this repo publishes to, e.g.
                    https://savyasachin.github.io/tech-digest_theodoobin/

Optional environment variable:
  DIGEST_MODE    - "quick" (1 story per section) or "full" (5 per section,
                   default)
"""

import html
import os
import sys
from datetime import datetime, timezone

import feedparser
import requests

FEED_GROUPS = {
    "Odoo": [
        "https://github.com/odoo/odoo/releases.atom",
        "https://github.com/OCA/server-tools/releases.atom",
        "https://github.com/OCA/web/releases.atom",
        "https://github.com/OCA/account-invoicing/releases.atom",
        "https://github.com/OCA/purchase-workflow/releases.atom",
        "https://hnrss.org/newest?q=Odoo",
        "https://www.reddit.com/r/Odoo/.rss",
    ],
    "Tech & World": [
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
        "https://hnrss.org/frontpage",
        "http://feeds.bbci.co.uk/news/world/rss.xml",
    ],
}

MODE_SETTINGS = {
    "quick": {"max_per_group": 1, "label": "Quick Check"},
    "full": {"max_per_group": 5, "label": "Full Digest"},
}


def fetch_group_stories(feed_urls, max_items):
    seen = set()
    stories = []

    for feed_url in feed_urls:
        parsed = feedparser.parse(feed_url)
        source_name = parsed.feed.get("title", "") if hasattr(parsed, "feed") else ""
        for entry in parsed.entries:
            title = getattr(entry, "title", "").strip()
            link = getattr(entry, "link", "").strip()
            if not title or not link:
                continue

            key = title.lower()
            if key in seen:
                continue
            seen.add(key)

            published = None
            for attr in ("published_parsed", "updated_parsed"):
                value = getattr(entry, attr, None)
                if value:
                    published = datetime(*value[:6], tzinfo=timezone.utc)
                    break
            if published is None:
                published = datetime.now(timezone.utc)

            stories.append(
                {
                    "title": title,
                    "link": link,
                    "published": published,
                    "source": source_name,
                }
            )

    stories.sort(key=lambda s: s["published"], reverse=True)
    return stories[:max_items]


def render_story_card(story):
    age = datetime.now(timezone.utc) - story["published"]
    hours = int(age.total_seconds() // 3600)
    if hours < 1:
        age_label = "just now"
    elif hours < 24:
        age_label = f"{hours}h ago"
    else:
        age_label = f"{hours // 24}d ago"

    title = html.escape(story["title"])
    link = html.escape(story["link"], quote=True)
    source = html.escape(story["source"]) if story["source"] else ""

    return f"""
      <a class="card" href="{link}" target="_blank" rel="noopener">
        <div class="card-title">{title}</div>
        <div class="card-meta">
          <span class="card-source">{source}</span>
          <span class="card-age">{age_label}</span>
        </div>
      </a>
    """


def render_section(group_name, stories):
    if not stories:
        cards_html = '<p class="empty">No fresh items right now.</p>'
    else:
        cards_html = "\n".join(render_story_card(s) for s in stories)

    return f"""
    <section>
      <h2>{html.escape(group_name)}</h2>
      <div class="cards">
        {cards_html}
      </div>
    </section>
    """


def build_page(mode):
    settings = MODE_SETTINGS.get(mode, MODE_SETTINGS["full"])
    max_per_group = settings["max_per_group"]
    label = settings["label"]

    now_qatar_label = datetime.now().strftime("%A, %d %B - %H:%M")

    sections_html = []
    for group_name, feed_urls in FEED_GROUPS.items():
        stories = fetch_group_stories(feed_urls, max_per_group)
        sections_html.append(render_section(group_name, stories))

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(label)} - {html.escape(now_qatar_label)}</title>
<style>
  :root {{
    color-scheme: light dark;
    --bg: #0b0f14;
    --card-bg: #151b23;
    --text: #e8edf2;
    --muted: #8a97a6;
    --accent: #6ea8fe;
    --border: #232c36;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    padding: 24px 16px 48px;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    max-width: 640px;
    margin-left: auto;
    margin-right: auto;
  }}
  header {{
    margin-bottom: 28px;
  }}
  header .eyebrow {{
    color: var(--accent);
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }}
  header h1 {{
    margin: 4px 0 0;
    font-size: 26px;
    font-weight: 700;
  }}
  header .timestamp {{
    color: var(--muted);
    font-size: 14px;
    margin-top: 6px;
  }}
  section {{
    margin-bottom: 32px;
  }}
  section h2 {{
    font-size: 18px;
    font-weight: 700;
    margin: 0 0 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
  }}
  .cards {{
    display: flex;
    flex-direction: column;
    gap: 10px;
  }}
  .card {{
    display: block;
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 14px 16px;
    text-decoration: none;
    color: var(--text);
    transition: border-color 0.15s ease;
  }}
  .card:active {{
    border-color: var(--accent);
  }}
  .card-title {{
    font-size: 15px;
    font-weight: 600;
    line-height: 1.4;
    margin-bottom: 8px;
  }}
  .card-meta {{
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    color: var(--muted);
  }}
  .empty {{
    color: var(--muted);
    font-size: 14px;
    font-style: italic;
    margin: 0;
  }}
  footer {{
    color: var(--muted);
    font-size: 12px;
    text-align: center;
    margin-top: 24px;
  }}
</style>
</head>
<body>
  <header>
    <div class="eyebrow">{html.escape(label)}</div>
    <h1>Daily Digest</h1>
    <div class="timestamp">{html.escape(now_qatar_label)} (Asia/Qatar)</div>
  </header>

  {"".join(sections_html)}

  <footer>Generated automatically &middot; refreshes twice a day</footer>
</body>
</html>
"""
    return page


def send_teaser_notification(mode, page_url):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print("Missing NTFY_TOPIC environment variable.", file=sys.stderr)
        sys.exit(1)

    settings = MODE_SETTINGS.get(mode, MODE_SETTINGS["full"])
    label = settings["label"]
    time_label = datetime.now().strftime("%H:%M")

    payload = {
        "topic": topic,
        "title": f"{label} ready",
        "message": f"Your {label.lower()} for {time_label} is up. Tap to open.",
        "click": page_url,
        "tags": ["newspaper"],
        "priority": 3,
        "actions": [
            {"action": "view", "label": "Open Digest", "url": page_url, "clear": False}
        ],
    }

    response = requests.post("https://ntfy.sh/", json=payload, timeout=30)
    print(f"ntfy response ({response.status_code}): {response.text[:300]}")
    response.raise_for_status()


def main():
    mode = os.environ.get("DIGEST_MODE", "full").strip().lower()
    page_url = os.environ.get("PAGES_URL")

    if not page_url:
        print("Missing PAGES_URL environment variable.", file=sys.stderr)
        sys.exit(1)

    page_html = build_page(mode)

    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(page_html)

    print(f"Wrote docs/index.html (mode={mode})")

    send_teaser_notification(mode, page_url)


if __name__ == "__main__":
    main()

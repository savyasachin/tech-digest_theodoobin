"""
Fetches fresh Odoo-ecosystem news plus general tech/world headlines from free
RSS/Atom feeds, picks the best few from each group, formats a short message
(always including links), and pushes it to your iPhone as a free notification
via ntfy.sh (https://ntfy.sh) - no account, no card, no phone-number linking.

Required environment variable (set as a GitHub Actions secret):
  NTFY_TOPIC   - your private topic name, e.g. yourname-odoo-digest-7f3k2
                 (must match exactly what you subscribed to in the ntfy app)

Optional environment variable:
  DIGEST_MODE  - "quick" (1 story per section) or "full" (3 per section,
                 default)
"""

import os
import sys
from datetime import datetime, timezone

import feedparser
import requests

FEED_GROUPS = {
    "\U0001F527 Odoo": [
        "https://github.com/odoo/odoo/releases.atom",
        "https://github.com/OCA/server-tools/releases.atom",
        "https://github.com/OCA/web/releases.atom",
        "https://github.com/OCA/account-invoicing/releases.atom",
        "https://github.com/OCA/purchase-workflow/releases.atom",
        "https://news.google.com/rss/search?q=Odoo&hl=en-US&gl=US&ceid=US:en",
    ],
    "\U0001F310 Tech & World": [
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
        "https://hnrss.org/frontpage",
        "http://feeds.bbci.co.uk/news/world/rss.xml",
    ],
}

MODE_SETTINGS = {
    "quick": {"max_per_group": 1, "label": "Quick Check"},
    "full": {"max_per_group": 3, "label": "Full Digest"},
}


def fetch_group_stories(feed_urls, max_items):
    seen = set()
    stories = []

    for feed_url in feed_urls:
        parsed = feedparser.parse(feed_url)
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

            stories.append({"title": title, "link": link, "published": published})

    stories.sort(key=lambda s: s["published"], reverse=True)
    return stories[:max_items]


def build_message(mode):
    settings = MODE_SETTINGS.get(mode, MODE_SETTINGS["full"])
    max_per_group = settings["max_per_group"]
    label = settings["label"]

    today_label = datetime.now().strftime("%A, %d %B")
    title = f"{label} - {today_label}"
    lines = []

    any_stories = False
    for group_name, feed_urls in FEED_GROUPS.items():
        stories = fetch_group_stories(feed_urls, max_per_group)
        lines.append(group_name)
        if not stories:
            lines.append("No fresh items right now.")
        else:
            any_stories = True
            for idx, story in enumerate(stories, start=1):
                # Title and link are always both included, even in quick mode.
                lines.append(f"{idx}. {story['title']}")
                lines.append(story["link"])
        lines.append("")

    if not any_stories:
        lines.append("Nothing fresh across any feed right now.")

    return title, "\n".join(lines).strip()


def send_notification(title, message):
    topic = os.environ.get("NTFY_TOPIC")

    if not topic:
        print("Missing NTFY_TOPIC environment variable.", file=sys.stderr)
        sys.exit(1)

    payload = {
        "topic": topic,
        "title": title,
        "message": message,
        "tags": ["newspaper"],
        "priority": 3,
    }

    response = requests.post("https://ntfy.sh/", json=payload, timeout=30)
    print(f"ntfy response ({response.status_code}): {response.text[:300]}")
    response.raise_for_status()


def main():
    mode = os.environ.get("DIGEST_MODE", "full").strip().lower()
    title, message = build_message(mode)
    print(f"---- Notification to send (mode={mode}) ----")
    print(f"Title: {title}")
    print(message)
    print("--------------------------")
    send_notification(title, message)


if __name__ == "__main__":
    main()

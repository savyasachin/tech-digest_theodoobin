"""
Fetches fresh Odoo-ecosystem news plus general tech/world headlines from free
RSS/Atom feeds, picks the best few from each group, shortens long links,
formats a clean Markdown message with quick-tap action buttons, and pushes it
to your iPhone as a free notification via ntfy.sh (https://ntfy.sh) - no
account, no card, no phone-number linking.

Note: Markdown (bold, links) only renders once you open the message inside
the ntfy app. The iOS lock-screen/notification-center preview always shows
plain text for any app - that's an OS limitation, not something this script
controls.

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
    "Odoo": [
        "https://github.com/odoo/odoo/releases.atom",
        "https://github.com/OCA/server-tools/releases.atom",
        "https://github.com/OCA/web/releases.atom",
        "https://github.com/OCA/account-invoicing/releases.atom",
        "https://github.com/OCA/purchase-workflow/releases.atom",
        "https://hnrss.org/newest?q=Odoo",   # direct links, no redirect junk
        "https://www.reddit.com/r/Odoo/.rss",  # direct links, no redirect junk
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
    "full": {"max_per_group": 3, "label": "Full Digest"},
}

MAX_TITLE_WORDS = 16
MAX_ACTION_LABEL_CHARS = 28
# TinyURL silently fails on very long URLs - skip shortening attempts past
# this length rather than wasting a request that will just fall through.
MAX_SHORTENABLE_LENGTH = 1800


def shorten_url(long_url):
    """Shorten a URL with TinyURL's free, keyless API. Falls back to the
    original URL if it's too long to shorten or the request fails."""
    if len(long_url) > MAX_SHORTENABLE_LENGTH:
        return long_url
    try:
        response = requests.get(
            "https://tinyurl.com/api-create.php",
            params={"url": long_url},
            timeout=10,
        )
        response.raise_for_status()
        short = response.text.strip()
        if short.startswith("http") and len(short) < len(long_url):
            return short
    except requests.RequestException:
        pass
    return long_url


def clean_title(title, max_words=MAX_TITLE_WORDS):
    words = title.split()
    if len(words) > max_words:
        title = " ".join(words[:max_words]) + "..."
    return title


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


def build_message_and_actions(mode):
    settings = MODE_SETTINGS.get(mode, MODE_SETTINGS["full"])
    max_per_group = settings["max_per_group"]
    label = settings["label"]

    today_label = datetime.now().strftime("%A, %d %B")
    title = f"{label} - {today_label}"
    lines = []
    actions = []
    group_names = list(FEED_GROUPS.keys())

    any_stories = False
    for idx, group_name in enumerate(group_names):
        stories = fetch_group_stories(FEED_GROUPS[group_name], max_per_group)
        lines.append(f"**{group_name}**")

        if not stories:
            lines.append("_No fresh items right now._")
        else:
            any_stories = True
            for story_idx, story in enumerate(stories):
                short_link = shorten_url(story["link"])
                clean = clean_title(story["title"])
                lines.append(f"- [{clean}]({short_link})")

                if story_idx == 0 and len(actions) < 3:
                    button_label = f"{group_name}: {clean_title(story['title'], max_words=5)}"
                    if len(button_label) > MAX_ACTION_LABEL_CHARS:
                        button_label = button_label[: MAX_ACTION_LABEL_CHARS - 1] + "…"
                    actions.append(
                        {
                            "action": "view",
                            "label": button_label,
                            "url": short_link,
                            "clear": False,
                        }
                    )

        if idx < len(group_names) - 1:
            lines.append("")
            lines.append("---")
        lines.append("")

    if not any_stories:
        lines.append("Nothing fresh across any feed right now.")

    message = "\n".join(lines).strip()
    return title, message, actions


def send_notification(title, message, actions):
    topic = os.environ.get("NTFY_TOPIC")

    if not topic:
        print("Missing NTFY_TOPIC environment variable.", file=sys.stderr)
        sys.exit(1)

    payload = {
        "topic": topic,
        "title": title,
        "message": message,
        "markdown": True,
        "tags": ["newspaper"],
        "priority": 3,
    }
    if actions:
        payload["actions"] = actions

    response = requests.post("https://ntfy.sh/", json=payload, timeout=30)
    print(f"ntfy response ({response.status_code}): {response.text[:300]}")
    response.raise_for_status()


def main():
    mode = os.environ.get("DIGEST_MODE", "full").strip().lower()
    title, message, actions = build_message_and_actions(mode)
    print(f"---- Notification to send (mode={mode}) ----")
    print(f"Title: {title}")
    print(message)
    print(f"Actions: {actions}")
    print("--------------------------")
    send_notification(title, message, actions)


if __name__ == "__main__":
    main()

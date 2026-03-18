#!/usr/bin/env python3
"""
Social Media Feed Crawler
Crawls configured platforms for the past 24h and populates the KANBAN board.

Usage:
    python crawl_feeds.py                  # normal run
    python crawl_feeds.py --dry-run        # preview without writing
    python crawl_feeds.py --config other.yaml
"""

import os
import re
import sys
import json
import yaml
import logging
import argparse
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dataclasses import dataclass, field

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Post:
    platform: str
    author: str
    author_display: str
    content: str        # short snippet / title
    url: str
    posted_at: datetime
    media_type: str = "text"  # text | video | image


PLATFORM_ICONS = {
    "twitter_x":    "𝕏",
    "youtube":      "▶",
    "weibo":        "微",
    "xiaohongshu":  "🍠",
    "threads":      "𝕋",
}


# ---------------------------------------------------------------------------
# Platform crawlers
# ---------------------------------------------------------------------------

class TwitterCrawler:
    PLATFORM = "twitter_x"

    def __init__(self, cfg: dict):
        self.bearer_token = cfg.get("bearer_token", "")
        self.following = cfg.get("following", [])

    def fetch(self, lookback_hours: int) -> list[Post]:
        if not self.bearer_token or "YOUR_" in self.bearer_token:
            logger.warning("Twitter/X: no bearer token — skipping")
            return []
        try:
            import requests
        except ImportError:
            logger.error("Twitter/X: install requests → pip install requests")
            return []

        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        since = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).isoformat()
        posts: list[Post] = []

        for account in self.following:
            username = account["username"]
            display = account.get("display_name", username)

            r = requests.get(
                f"https://api.twitter.com/2/users/by/username/{username}",
                headers=headers, timeout=10,
            )
            if r.status_code != 200:
                logger.warning(f"Twitter/X: can't resolve user @{username} ({r.status_code})")
                continue
            uid = r.json()["data"]["id"]

            r = requests.get(
                f"https://api.twitter.com/2/users/{uid}/tweets",
                headers=headers, timeout=10,
                params={
                    "start_time": since,
                    "tweet.fields": "created_at,text",
                    "max_results": 10,
                    "exclude": "retweets,replies",
                },
            )
            if r.status_code != 200:
                logger.warning(f"Twitter/X: tweets fetch failed for @{username} ({r.status_code})")
                continue

            for tweet in r.json().get("data", []):
                posts.append(Post(
                    platform=self.PLATFORM,
                    author=username,
                    author_display=display,
                    content=tweet["text"][:200],
                    url=f"https://x.com/{username}/status/{tweet['id']}",
                    posted_at=datetime.fromisoformat(tweet["created_at"].replace("Z", "+00:00")),
                ))

        logger.info(f"Twitter/X: {len(posts)} new posts")
        return posts


class YouTubeCrawler:
    PLATFORM = "youtube"

    def __init__(self, cfg: dict):
        self.api_key = cfg.get("api_key", "")
        self.channels = cfg.get("channels", [])

    def fetch(self, lookback_hours: int) -> list[Post]:
        if not self.api_key or "YOUR_" in self.api_key:
            logger.warning("YouTube: no API key — skipping")
            return []
        try:
            import requests
        except ImportError:
            logger.error("YouTube: install requests → pip install requests")
            return []

        since = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        posts: list[Post] = []

        for channel in self.channels:
            cid = channel["channel_id"]
            display = channel.get("display_name", cid)

            r = requests.get(
                "https://www.googleapis.com/youtube/v3/search",
                timeout=10,
                params={
                    "key": self.api_key,
                    "channelId": cid,
                    "part": "snippet",
                    "order": "date",
                    "publishedAfter": since,
                    "type": "video",
                    "maxResults": 10,
                },
            )
            if r.status_code != 200:
                logger.warning(f"YouTube: API error for {display} ({r.status_code})")
                continue

            for item in r.json().get("items", []):
                snip = item["snippet"]
                vid = item["id"]["videoId"]
                posts.append(Post(
                    platform=self.PLATFORM,
                    author=cid,
                    author_display=display,
                    content=snip.get("title", ""),
                    url=f"https://www.youtube.com/watch?v={vid}",
                    posted_at=datetime.fromisoformat(snip["publishedAt"].replace("Z", "+00:00")),
                    media_type="video",
                ))

        logger.info(f"YouTube: {len(posts)} new videos")
        return posts


class WeiboCrawler:
    PLATFORM = "weibo"

    def __init__(self, cfg: dict):
        self.access_token = cfg.get("access_token", "")
        self.following = cfg.get("following", [])

    def fetch(self, lookback_hours: int) -> list[Post]:
        if not self.access_token or "YOUR_" in self.access_token:
            logger.warning("Weibo: no access token — skipping")
            return []
        try:
            import requests
        except ImportError:
            logger.error("Weibo: install requests → pip install requests")
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        posts: list[Post] = []

        for account in self.following:
            uid = account.get("uid", "")
            display = account.get("display_name", uid)

            r = requests.get(
                "https://api.weibo.com/2/statuses/user_timeline.json",
                timeout=10,
                params={"access_token": self.access_token, "uid": uid, "count": 20},
            )
            if r.status_code != 200:
                logger.warning(f"Weibo: API error for {display} ({r.status_code})")
                continue

            for status in r.json().get("statuses", []):
                created = datetime.strptime(status["created_at"], "%a %b %d %H:%M:%S %z %Y")
                if created < cutoff:
                    continue
                posts.append(Post(
                    platform=self.PLATFORM,
                    author=uid,
                    author_display=display,
                    content=status.get("text", "")[:200],
                    url=f"https://weibo.com/{uid}/{status['id']}",
                    posted_at=created,
                ))

        logger.info(f"Weibo: {len(posts)} new posts")
        return posts


class ThreadsCrawler:
    PLATFORM = "threads"

    def __init__(self, cfg: dict):
        self.access_token = cfg.get("access_token", "")
        self.following = cfg.get("following", [])

    def fetch(self, lookback_hours: int) -> list[Post]:
        if not self.access_token or "YOUR_" in self.access_token:
            logger.warning("Threads: no access token — skipping")
            return []
        try:
            import requests
        except ImportError:
            logger.error("Threads: install requests → pip install requests")
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        posts: list[Post] = []

        for account in self.following:
            uid = account.get("user_id", "")
            display = account.get("display_name", uid)

            r = requests.get(
                f"https://graph.threads.net/v1.0/{uid}/threads",
                timeout=10,
                params={
                    "access_token": self.access_token,
                    "fields": "id,text,timestamp,permalink",
                    "limit": 20,
                },
            )
            if r.status_code != 200:
                logger.warning(f"Threads: API error for {display} ({r.status_code})")
                continue

            for item in r.json().get("data", []):
                created = datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))
                if created < cutoff:
                    continue
                posts.append(Post(
                    platform=self.PLATFORM,
                    author=uid,
                    author_display=display,
                    content=item.get("text", "")[:200],
                    url=item.get("permalink", ""),
                    posted_at=created,
                ))

        logger.info(f"Threads: {len(posts)} new posts")
        return posts


class XiaohongshuCrawler:
    """
    Uses xhs-cli (github.com/jackwener/xhs-cli) to fetch user posts.

    Setup:
        uv tool install xhs-cli   (or: pipx install xhs-cli)
        xhs login                 (one-time browser cookie extraction)

    Since xhs-cli's user-posts output doesn't include reliable timestamps,
    we use a seen-post-ID cache to surface only new posts each run.
    Cache file: _System/Scripts/.xhs_seen.json
    """
    PLATFORM = "xiaohongshu"
    CACHE_FILE = Path(__file__).parent / ".xhs_seen.json"

    def __init__(self, cfg: dict):
        self.following = cfg.get("following", [])
        self._seen: set[str] = self._load_cache()

    def _load_cache(self) -> set[str]:
        if self.CACHE_FILE.exists():
            try:
                return set(json.loads(self.CACHE_FILE.read_text(encoding="utf-8")))
            except Exception:
                pass
        return set()

    def _save_cache(self) -> None:
        self.CACHE_FILE.write_text(
            json.dumps(sorted(self._seen), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _xhs_available(self) -> bool:
        result = subprocess.run(["xhs", "--version"], capture_output=True)
        return result.returncode == 0

    def fetch(self, lookback_hours: int) -> list[Post]:
        if not self._xhs_available():
            logger.warning(
                "XHS: xhs-cli not found — install with: uv tool install xhs-cli  then: xhs login"
            )
            return []

        posts: list[Post] = []
        new_seen: set[str] = set()

        for account in self.following:
            uid = account.get("user_id", "")
            display = account.get("display_name", uid)

            try:
                result = subprocess.run(
                    ["xhs", "user-posts", uid, "--json"],
                    capture_output=True, text=True, timeout=30,
                )
            except subprocess.TimeoutExpired:
                logger.warning(f"XHS: timeout fetching {display}")
                continue
            except FileNotFoundError:
                logger.warning("XHS: xhs command not found in PATH")
                break

            if result.returncode != 0:
                logger.warning(f"XHS: xhs user-posts failed for {display}: {result.stderr.strip()[:200]}")
                continue

            try:
                items = json.loads(result.stdout)
            except json.JSONDecodeError:
                logger.warning(f"XHS: could not parse JSON for {display}")
                continue

            if not isinstance(items, list):
                items = items.get("data", items.get("notes", []))

            for item in items:
                # Handle both camelCase and snake_case field names
                note_id = item.get("id") or item.get("noteId") or item.get("note_id", "")
                if not note_id:
                    continue

                new_seen.add(note_id)

                # Skip already-seen posts
                if note_id in self._seen:
                    continue

                card = item.get("noteCard") or item.get("note_card") or item
                title = (
                    card.get("displayTitle")
                    or card.get("display_title")
                    or card.get("title")
                    or item.get("title", "")
                )
                media_type = "video" if item.get("type") == "video" else "text"
                xsec = item.get("xsecToken") or item.get("xsec_token", "")
                url = f"https://www.xiaohongshu.com/explore/{note_id}"
                if xsec:
                    url += f"?xsec_token={xsec}"

                posts.append(Post(
                    platform=self.PLATFORM,
                    author=uid,
                    author_display=display,
                    content=title[:200],
                    url=url,
                    posted_at=datetime.now(timezone.utc),  # xhs-cli doesn't expose created_at
                    media_type=media_type,
                ))

        # Persist cache — add newly seen IDs, keep old ones too
        self._seen.update(new_seen)
        self._save_cache()

        logger.info(f"XHS: {len(posts)} new posts (unseen since last run)")
        return posts


# ---------------------------------------------------------------------------
# Kanban + daily note writers
# ---------------------------------------------------------------------------

def format_card(post: Post) -> str:
    icon = PLATFORM_ICONS.get(post.platform, "🔗")
    time_str = post.posted_at.strftime("%H:%M")
    snippet = post.content[:120].replace("\n", " ").replace("|", "｜")
    if len(post.content) > 120:
        snippet += "…"
    return (
        f"- [ ] {icon} **{post.author_display}** · {time_str}  \n"
        f"  [{snippet}]({post.url})"
    )


def update_kanban(posts: list[Post], vault_path: str, kanban_rel: str) -> None:
    board = Path(vault_path) / kanban_rel
    if not board.exists():
        logger.error(f"Kanban board not found: {board}")
        return

    content = board.read_text(encoding="utf-8")
    date_line = f"\n<!-- Crawled {datetime.now().strftime('%Y-%m-%d %H:%M')} — {len(posts)} posts -->\n"
    cards = "\n".join(format_card(p) for p in posts)
    new_block = f"<!-- CRAWL_START -->{date_line}{cards}\n<!-- CRAWL_END -->"

    if "<!-- CRAWL_START -->" in content:
        content = re.sub(
            r"<!-- CRAWL_START -->.*?<!-- CRAWL_END -->",
            new_block,
            content,
            flags=re.DOTALL,
        )
    else:
        content = content.replace(
            "## Active\n",
            f"## Active\n\n{new_block}\n",
        )

    board.write_text(content, encoding="utf-8")
    logger.info(f"Kanban updated → {len(posts)} cards in Active")


def update_daily_note(posts: list[Post], vault_path: str, daily_rel: str) -> None:
    today = datetime.now()
    note = Path(vault_path) / daily_rel / today.strftime("%Y") / f"{today.strftime('%Y-%m-%d')}.md"
    note.parent.mkdir(parents=True, exist_ok=True)

    # Group by platform
    by_platform: dict[str, list[Post]] = {}
    for p in posts:
        by_platform.setdefault(p.platform, []).append(p)

    lines = [f"## Morning Feed Summary\n"]
    for platform, plist in by_platform.items():
        icon = PLATFORM_ICONS.get(platform, "🔗")
        lines.append(f"\n### {icon} {platform.replace('_', ' ').title()} — {len(plist)} new\n")
        for p in plist[:5]:
            lines.append(f"- [{p.author_display}]({p.url}): {p.content[:90]}{'…' if len(p.content) > 90 else ''}")
        if len(plist) > 5:
            lines.append(f"- _…and {len(plist) - 5} more in [[02-KANBAN/Feed-Board|KANBAN]]_")
    summary = "\n".join(lines)

    if note.exists():
        existing = note.read_text(encoding="utf-8")
        if "## Morning Feed Summary" in existing:
            existing = re.sub(
                r"## Morning Feed Summary.*?(?=\n## |\Z)",
                summary + "\n\n",
                existing,
                flags=re.DOTALL,
            )
        else:
            existing = summary + "\n\n" + existing
        note.write_text(existing, encoding="utf-8")
    else:
        template = Path(vault_path) / "_System/Templates/daily-note.md"
        base = ""
        if template.exists():
            base = template.read_text(encoding="utf-8")
            base = base.replace("{{date}}", today.strftime("%Y-%m-%d"))
            base = base.replace("{{day}}", today.strftime("%A"))
            # Strip placeholder summary line
            base = re.sub(r"_Auto-populated.*?\n", "", base)
        note.write_text(summary + "\n\n" + base, encoding="utf-8")

    logger.info(f"Daily note updated → {note}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl social media feeds → KANBAN")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Print cards, don't write files")
    args = parser.parse_args()

    cfg_path = Path(__file__).parent / args.config
    if not cfg_path.exists():
        logger.error(f"Config not found: {cfg_path}")
        sys.exit(1)

    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)

    settings = cfg.get("settings", {})
    vault = settings.get("vault_path", str(Path(__file__).parent.parent.parent))
    lookback = settings.get("lookback_hours", 24)
    kanban = settings.get("kanban_board", "02-KANBAN/Feed-Board.md")
    daily = settings.get("daily_notes_path", "01-Daily")

    p = cfg.get("platforms", {})
    crawlers = []
    if p.get("twitter_x", {}).get("enabled"):   crawlers.append(TwitterCrawler(p["twitter_x"]))
    if p.get("youtube", {}).get("enabled"):      crawlers.append(YouTubeCrawler(p["youtube"]))
    if p.get("weibo", {}).get("enabled"):        crawlers.append(WeiboCrawler(p["weibo"]))
    if p.get("threads", {}).get("enabled"):      crawlers.append(ThreadsCrawler(p["threads"]))
    if p.get("xiaohongshu", {}).get("enabled"):  crawlers.append(XiaohongshuCrawler(p["xiaohongshu"]))

    if not crawlers:
        logger.warning("No platforms enabled. Edit config.yaml and set enabled: true.")
        return

    all_posts: list[Post] = []
    for crawler in crawlers:
        all_posts.extend(crawler.fetch(lookback))

    all_posts.sort(key=lambda p: p.posted_at, reverse=True)

    if args.dry_run:
        print(f"\n{'─'*60}")
        print(f"  DRY RUN — {len(all_posts)} posts")
        print(f"{'─'*60}\n")
        for post in all_posts:
            print(format_card(post))
            print()
        return

    if all_posts:
        update_kanban(all_posts, vault, kanban)
        update_daily_note(all_posts, vault, daily)
        logger.info(f"Done — {len(all_posts)} posts added")
    else:
        logger.info("No new posts in the past 24h.")


if __name__ == "__main__":
    main()

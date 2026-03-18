#!/usr/bin/env python3
"""
Journal Assistant — powered by Claude

Takes your raw note or thought, structures it, and appends it to today's daily journal.

Usage:
    python journal_assistant.py "Karpathy's point about calibration > accuracy really clicked"

    # With a manually shared link:
    python journal_assistant.py --link "https://x.com/..." "My take on this thread"

    # Route to the ad-hoc section (not from the feed queue):
    python journal_assistant.py --adhoc "Shower thought: what if we treat tech debt like interest rate?"

    # Route to Ideas section:
    python journal_assistant.py --ideas "Half-baked: a VSCode extension that surfaces related vault notes inline"

    # Pipe from stdin:
    pbpaste | python journal_assistant.py --stdin
"""

import os
import re
import sys
import yaml
import argparse
import logging
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

SECTIONS = {
    "notes":  "## Notes & Thoughts",
    "adhoc":  "## Ad-hoc & Serendipity",
    "ideas":  "## Ideas Sparked",
}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config() -> dict:
    cfg_path = Path(__file__).parent / "config.yaml"
    if cfg_path.exists():
        with open(cfg_path) as f:
            return yaml.safe_load(f)
    return {}


def today_note_path(cfg: dict) -> Path:
    settings = cfg.get("settings", {})
    vault = settings.get("vault_path", str(Path(__file__).parent.parent.parent))
    daily = settings.get("daily_notes_path", "01-Daily")
    now = datetime.now()
    return Path(vault) / daily / now.strftime("%Y") / f"{now.strftime('%Y-%m-%d')}.md"


# ---------------------------------------------------------------------------
# Claude call
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a personal knowledge assistant for a software engineer's Obsidian daily journal.

Your task: take the user's raw note or thought and produce a clean, well-structured markdown \
snippet to append to their daily journal.

Rules:
- Preserve the user's voice — don't over-formalize or over-expand
- Extract the key insight or question at the core
- Use [[wikilinks]] for named concepts, people, technologies, or projects worth cross-referencing
- Add 2-4 relevant #tags (e.g. #insight #engineering #ai #product #question #idea #resource)
- If a URL was provided, embed it cleanly in the note
- Output ONLY the markdown snippet — no preamble, no explanation, no code fences
- Use this exact format:

### HH:MM — Short descriptive title

Body of the note. Keep it tight. One key insight per paragraph.

> Memorable quote or highlight if applicable

**Tags:** #tag1 #tag2 #tag3
"""


def call_claude(user_input: str, link: str | None, existing_note: str) -> str:
    try:
        import anthropic
    except ImportError:
        logger.error("anthropic SDK not installed — run: pip install anthropic")
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY environment variable not set")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    now = datetime.now()

    link_line = f"\nLinked URL: {link}" if link else ""
    context_tail = existing_note[-2000:] if existing_note else "(no entries yet today)"

    user_msg = f"""\
Current time: {now.strftime("%H:%M")} on {now.strftime("%Y-%m-%d, %A")}

My note:
{link_line}
{user_input}

Existing journal context (do not repeat what is already there):
---
{context_tail}
---

Produce the markdown snippet to append."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    return response.content[0].text.strip()


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def read_note(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def append_to_section(path: Path, snippet: str, section_header: str, cfg: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        content = path.read_text(encoding="utf-8")
    else:
        vault = cfg.get("settings", {}).get("vault_path", str(path.parent.parent.parent))
        tpl = Path(vault) / "_System/Templates/daily-note.md"
        if tpl.exists():
            content = tpl.read_text(encoding="utf-8")
            now = datetime.now()
            content = content.replace("{{date}}", now.strftime("%Y-%m-%d"))
            content = content.replace("{{day}}", now.strftime("%A"))
        else:
            now = datetime.now()
            content = (
                f"# {now.strftime('%Y-%m-%d')} — {now.strftime('%A')}\n\n"
                + "\n\n".join(f"{h}\n" for h in SECTIONS.values())
                + "\n"
            )

    if section_header in content:
        # Find the section and append before the next ## heading
        parts = content.split(section_header, 1)
        rest = parts[1]
        next_h = re.search(r"\n## ", rest[1:])
        if next_h:
            idx = next_h.start() + 1  # +1 for the sliced leading char
            new_content = parts[0] + section_header + rest[:idx] + "\n\n" + snippet + "\n" + rest[idx:]
        else:
            new_content = content.rstrip() + "\n\n" + snippet + "\n"
    else:
        new_content = content.rstrip() + f"\n\n{section_header}\n\n{snippet}\n"

    path.write_text(new_content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Append structured notes to today's journal via Claude.")
    parser.add_argument("text", nargs="?", help="Your raw note or thought")
    parser.add_argument("--link", "-l", metavar="URL", help="URL of the resource you're noting")
    parser.add_argument("--stdin", "-s", action="store_true", help="Read note from stdin")
    parser.add_argument("--adhoc",  "-a", action="store_true", help="Route to Ad-hoc & Serendipity section")
    parser.add_argument("--ideas",  "-i", action="store_true", help="Route to Ideas Sparked section")
    parser.add_argument("--yes",    "-y", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    # Determine input
    if args.stdin:
        user_input = sys.stdin.read().strip()
    elif args.text:
        user_input = args.text
    else:
        parser.print_help()
        sys.exit(1)

    if not user_input:
        logger.error("Empty input.")
        sys.exit(1)

    # Determine target section
    if args.ideas:
        section = SECTIONS["ideas"]
    elif args.adhoc:
        section = SECTIONS["adhoc"]
    else:
        section = SECTIONS["notes"]

    cfg = load_config()
    note_path = today_note_path(cfg)
    existing = read_note(note_path)

    print(f"\nProcessing with Claude → {section} …\n")
    snippet = call_claude(user_input, args.link, existing)

    print("─" * 60)
    print(snippet)
    print("─" * 60)
    print(f"\nTarget: {note_path.name}  →  {section}")

    if not args.yes:
        confirm = input("\nAppend? [Y/n] ").strip().lower()
        if confirm not in ("", "y", "yes"):
            print("Aborted.")
            return

    append_to_section(note_path, snippet, section, cfg)
    print(f"✓ Appended to {note_path}")


if __name__ == "__main__":
    main()

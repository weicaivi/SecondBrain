# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Vault Is

A personal knowledge management system (Obsidian vault) for a software engineer. It combines:
- **Daily journaling** structured by Claude (`journal_assistant.py`)
- **Social media feed aggregation** into a Kanban reading queue (`crawl_feeds.py`)
- **Long-term knowledge accumulation** in `03-Knowledge/`

The scripting layer lives in `_System/Scripts/`. Everything else is Obsidian markdown.

## Running the Scripts

All scripts are run from `_System/Scripts/` using the local venv:

```bash
cd _System/Scripts
source .venv/bin/activate

# Morning crawl — populates 02-KANBAN/Feed-Board.md and today's daily note
python crawl_feeds.py
python crawl_feeds.py --dry-run        # preview without writing

# Journal assistant — append a structured note to today's daily note
python journal_assistant.py "your raw thought here"
python journal_assistant.py --link "https://..." "your take"
python journal_assistant.py --adhoc "random shower thought"
python journal_assistant.py --ideas "half-baked idea"
python journal_assistant.py --yes "thought"   # skip confirmation prompt
pbpaste | python journal_assistant.py --stdin
```

`ANTHROPIC_API_KEY` must be set in the environment for `journal_assistant.py`.

## Architecture

### crawl_feeds.py
One crawler class per platform, all sharing the `Post` dataclass. Each crawler's `fetch(lookback_hours)` returns `list[Post]`. After all crawlers run, two writers are called:
- `update_kanban()` — replaces the `<!-- CRAWL_START -->…<!-- CRAWL_END -->` block in `Feed-Board.md`
- `update_daily_note()` — writes/replaces the `## Morning Feed Summary` section in today's note

**Platform-specific notes:**
- Twitter/X, YouTube, Weibo, Threads: API-based, credentials in `config.yaml`
- Xiaohongshu: uses `xhs` CLI (xhs-cli) via `subprocess`. No timestamps available from `user-posts`, so novelty is tracked via a **seen-post-ID cache** at `_System/Scripts/.xhs_seen.json`. First run surfaces everything; subsequent runs show only new posts.

### journal_assistant.py
Reads the existing daily note for context, calls Claude (`claude-sonnet-4-6`) with a structured system prompt, and appends the returned markdown snippet to the correct section (`## Notes & Thoughts`, `## Ad-hoc & Serendipity`, or `## Ideas Sparked`). The section insertion logic finds the target `## ` header and places the snippet before the next `## ` heading.

### config.yaml
Single source of truth for vault path, platform credentials, and followed accounts. Loaded by both scripts. The `settings.vault_path` key must match the actual vault location on disk.

## Vault Folder Conventions

| Folder | Purpose |
|--------|---------|
| `00-Inbox/` | Zero-friction capture; process weekly |
| `01-Daily/YYYY/YYYY-MM-DD.md` | Daily notes; auto-created by scripts if missing |
| `02-KANBAN/Feed-Board.md` | Kanban board (obsidian-kanban plugin, `board` type) |
| `03-Knowledge/` | Evergreen notes — Concepts, People, Tech subdirs |
| `04-Sources/` | Atomic source notes, one per article/video/post |
| `05-Projects/` | Active project folders |
| `_System/Templates/` | `daily-note.md` and `source-note.md` used by scripts |

## Obsidian Settings

| Setting | Value |
|---------|-------|
| Default attachment location | `04-Sources/` |
| Daily notes → New file location | `01-Daily/2026` |
| Daily notes → Template file | `_System/Templates/daily-note` |
| Kanban board type | `board` (not `basic`) — keep this in `Feed-Board.md` frontmatter |

The scripts construct daily note paths as `01-Daily/{YYYY}/{YYYY-MM-DD}.md`, which aligns with the Obsidian daily notes location. When the year rolls over, update both the Obsidian setting and `config.yaml` → `daily_notes_path` (or just update the Obsidian setting; the scripts derive the year dynamically).

Attachments dropped into Obsidian land in `04-Sources/` alongside source notes — that folder serves double duty as both structured source notes and raw attachment storage.

## Obsidian Plugins Installed

`obsidian-kanban`, `templater-obsidian`, `calendar`, `obsidian-git`, `terminal`

## Adding a New Platform Crawler

1. Add a class in `crawl_feeds.py` following the pattern: `__init__(self, cfg: dict)` + `fetch(self, lookback_hours: int) -> list[Post]`
2. Add its icon to `PLATFORM_ICONS`
3. Wire it up in `main()` with an `enabled` guard
4. Add the platform block to `config.yaml`

## XHS CLI Setup (one-time)

```bash
uv tool install xhs-cli   # or: pipx install xhs-cli
xhs login                 # extracts cookies from browser automatically
xhs status                # verify
```

# Second Brain — Software Engineer's Knowledge System

A minimal, automation-assisted PKM for daily reading, thinking, and knowledge accumulation.

---

## Folder Map

```
Vault/
├── 00-Inbox/          Fast capture — dump anything, process later
├── 01-Daily/          Daily journal notes (auto-populated + Claude-organized)
├── 02-KANBAN/         Social feed reading queue (Active → Done)
├── 03-Knowledge/      Evergreen notes: Concepts, People, Tech
├── 04-Sources/        Atomic source notes (one per article/video/post)
├── 05-Projects/       Active work and personal projects
├── 06-Archive/        Completed / no longer active
└── _System/           Templates, scripts, config
```

---

## Daily Workflow

### Morning (~5 min setup)
```bash
cd _System/Scripts
python crawl_feeds.py
```
This crawls all configured platforms for the past 24h and:
- Populates `02-KANBAN/Feed-Board.md` → **Active** column
- Writes a **Morning Feed Summary** to today's daily note

### Throughout the Day
Open `02-KANBAN/Feed-Board.md` and work through the **Active** list.

**While reading, text Claude your thoughts:**
```bash
python journal_assistant.py "Karpathy's point about LLM evals — calibration > accuracy really clicked"

# With a link (ad-hoc, not from the feed list):
python journal_assistant.py --link "https://x.com/..." "My hot take on this thread"

# Mark as ad-hoc/serendipity:
python journal_assistant.py --adhoc "Random shower thought about distributed systems"
```

Claude structures your raw note and appends it to today's journal in the right section.

**Move KANBAN tasks:**
- Finished → drag to **Done**
- Needs more time → drag to **Backlog**

### Weekly (optional)
Run a weekly synthesis prompt to distill journal notes → `03-Knowledge/` evergreen notes.

---

## Setup

### 1. Install dependencies
```bash
cd _System/Scripts
pip install -r requirements.txt
```

### 2. Set your API key
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```
Add to `~/.zshrc` or `~/.bashrc` to persist.

### 3. Configure followed accounts
Edit `_System/Scripts/config.yaml` — add your accounts per platform and set `enabled: true`.

### 4. Automate the morning crawl (optional)
```bash
# Run every morning at 7am
crontab -e
# Add: 0 7 * * * cd /Users/weicai/Desktop/Vault/_System/Scripts && python crawl_feeds.py
```

---

## Platform Notes

| Platform | API | Notes |
|----------|-----|-------|
| X/Twitter | Twitter API v2 — Bearer Token | Free tier: 500k reads/mo. Get at developer.twitter.com |
| YouTube | YouTube Data API v3 | Free quota sufficient. Get at console.cloud.google.com |
| Weibo | Weibo Open Platform | Requires app registration at open.weibo.com |
| Threads | Threads API (Basic) | Can only read posts from accounts that authorized your app |
| 小红书 (XHS) | xhs-cli (cookie-based) | `uv tool install xhs-cli` then `xhs login` — no API key needed |

### 小红书 Setup (xhs-cli)
```bash
uv tool install xhs-cli   # or: pipx install xhs-cli
xhs login                 # auto-extracts cookies from Chrome/Firefox/Edge/Brave
xhs status                # verify it worked
xhs user-posts USER_ID    # test fetching a creator's posts
```
New posts are detected by a **seen-post-ID cache** at `_System/Scripts/.xhs_seen.json` — on each run, only posts not seen before are surfaced. First run will appear to show everything; subsequent runs show only what's new.

---

## Improvement Ideas

- **Weekly synthesis**: Every Sunday, feed the week's journals to Claude and generate a `03-Knowledge/` evergreen note summarizing emerging patterns
- **People graph**: Auto-update `03-Knowledge/People/<name>.md` with each creator's evolving POV as you read
- **Idea temperature**: Tag half-baked ideas `#cold`, `#warm`, `#hot` and surface the hot ones for follow-up
- **Trend detection**: When 3+ people you follow post about the same topic, Claude creates a "convergence note"
- **Backlog aging**: Weekly script flags Backlog items older than 7 days — force a keep/discard decision
- **Topic filters**: Tag KANBAN cards by topic (`#ai`, `#product`, `#philosophy`) to filter by mood
- **Monthly letter**: Claude writes a "letter to future self" each month from your journal entries
- **Spaced repetition**: Use Obsidian's SR plugin on `03-Knowledge/` notes to actually internalize insights
- **Blog pipeline**: Mature `03-Knowledge/` notes → exported as blog drafts with one command
- **Connection surfacing**: When journaling, Claude surfaces 2-3 related notes from your vault you might connect

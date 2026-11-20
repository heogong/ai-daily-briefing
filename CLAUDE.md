## Project Overview

Automated AI news briefing generator that collects RSS news, analyzes it with Claude API, and publishes a daily Korean-language HTML newsletter to GitHub Pages with optional email distribution.

**Live site:** heogong.github.io/ai-daily-briefing/
**Schedule:** cron-job.org calls the GitHub `workflow_dispatch` API daily at KST 06:00. Do NOT add a `schedule:` trigger to the workflow (causes duplicate runs/emails). See `SCHEDULING.md`.

## Running the Pipeline

```bash
# Install dependencies
pip install anthropic feedparser requests

# Generate today's briefing locally
python ai_daily_briefing.py

# Send email to subscribers
python send_email.py
```

**Required environment variables:**
- `ANTHROPIC_API_KEY` — Claude API key
- `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD` — for email distribution
- `GCP_TTS_KEY` — optional, for MP3 audio generation

Output files are written to `output/` (gitignored). The GitHub Actions workflow copies them to `docs/` for GitHub Pages.

## Architecture

The main pipeline (`ai_daily_briefing.py`) runs in 4 steps:

1. **RSS Collection** — Fetches from 6 feeds (Google News EN/KO, TechCrunch, VentureBeat, The Verge), filters to last 24h KST, deduplicates by title. Auto-expands timeframe if fewer than 5 articles found.

2. **Claude Analysis** — Sends collected articles to Claude Sonnet 4.6 with a system prompt that includes the full contents of `ISU_COMPANY.md`. The model selects 5 stories and returns structured JSON.

3. **JSON Parsing** — Triple-layer defense: regex extraction → auto-fix (unescaped quotes, HTML tags) → fallback ask Claude to repair.

4. **HTML/TTS Generation** — Renders dark-themed responsive HTML. Optionally generates Korean MP3 via GCP Text-to-Speech (Wavenet-D voice) with special character stripping and pronunciation substitutions.

**`ai_daily_briefing_openai.py`** is a parallel implementation using OpenAI gpt-4o instead of Claude — same pipeline, different API client.

## Key Files

| File | Purpose |
|------|---------|
| `ai_daily_briefing.py` | Main generator (Claude API) |
| `ai_daily_briefing_openai.py` | Alternative generator (OpenAI) |
| `send_email.py` | Gmail SMTP distribution |
| `ISU_COMPANY.md` | Company context injected into Claude system prompt each run |
| `subscribers.txt` | One email per line; lines starting with `#` are comments |
| `docs/` | GitHub Pages output (HTML, JSON, MP3 archives + index.html) |
| `.github/workflows/daily-briefing.yml` | CI/CD (`workflow_dispatch` only, `concurrency` guarded): generate → copy to docs/ → commit & push → send emails |
| `SCHEDULING.md` | External scheduler (cron-job.org) setup guide |

## JSON Output Schema

Claude returns JSON that gets parsed and used for both HTML rendering and archival:

```json
{
  "date": "2026.03.25 (수)",
  "one_liner": "one-sentence summary",
  "news": [
    {
      "number": 1,
      "category": "모델 릴리스|제품 업데이트|일자리·사회|산업 동향|글로벌 이슈",
      "title": "...",
      "body": "2-3 paragraph summary with **markdown emphasis**",
      "insight": "industry-wide implication",
      "isu_area": "AI 사업|디지털서비스|ESG|HR|안전|클라우드",
      "isu_tag": "[핵심 기회]|[제품 강화]|[영업 기회]|[리스크]|[모니터링]|[정부 사업]",
      "isu_insight": "ISU Systems-specific perspective"
    }
  ],
  "takeaways": ["insight 1", "insight 2", "insight 3"],
  "isu_summary": "ISU Systems synthesis (2-3 sentences)"
}
```

`**text**` markdown in `body` fields is converted to `<strong>` tags in the HTML renderer.

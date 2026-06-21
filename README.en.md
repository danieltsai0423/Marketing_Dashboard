<h1 align="center">Cross-Platform Social Content Intelligence Dashboard</h1>

<p align="center"><a href="./README.md">繁體中文</a> | <strong>English</strong></p>

> Collect trending short-form content across **YouTube, Instagram, Facebook, and Threads**, normalize it into a single data model, generate AI market-analysis reports, and push them to LINE — all from one local Streamlit app.

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white">
  <img alt="Streamlit" src="https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white">
  <img alt="Tests" src="https://img.shields.io/badge/tests-24%20passing-brightgreen">
  <img alt="i18n" src="https://img.shields.io/badge/i18n-繁中%20%2F%20EN-blue">
</p>

---

## Overview

A locally deployed market-intelligence system for social content. Enter keywords, pick the platforms, and the app fetches the top-performing posts/videos from four social platforms in parallel, normalizes the heterogeneous responses into a unified `UniversalContentModel`, and uses an LLM agent to produce an actionable Traditional-Chinese market report. It also supports weekly scheduling and LINE broadcast.

The dashboard started as a single-platform YouTube Shorts monitor and was refactored into a **general-purpose, multi-platform** architecture that works for any content niche (food, travel, fitness, beauty, …).

## Features

- **Four platforms, hybrid sources** — YouTube via the official Data API v3; Instagram / Facebook / Threads via Apify actors.
- **Unified data model** — one schema (`UniversalContentModel`) across platforms, with backward-compatible aliases so the UI, reports, and storage layers stay decoupled from any single source.
- **Parallel request routing** — a data router fans out to selected platforms concurrently (`ThreadPoolExecutor`); a single platform failure is isolated and surfaced, not fatal.
- **Inclusive UI components** — video platforms render as vertical thumbnails; Threads renders X-style text-first cards. Unified sorting handles content with no view count (sinks to bottom / falls back to likes).
- **Bilingual interface** — Traditional Chinese by default, switch to English live from the sidebar.
- **AI reports** — streamed Markdown reports (trends, breakout analysis, content ideas, risk notes) via OpenRouter (OpenAI-compatible).
- **Automation & delivery** — weekly `APScheduler` job and LINE broadcast.
- **Graceful degradation** — falls back to local JSONL/Markdown when Supabase isn't configured; missing API keys are shown in the sidebar without breaking other features.

## Architecture

```
[ keywords & platform selection ]
              │
              ▼
[ Data Router ] ── ThreadPoolExecutor (parallel fan-out)
      ├── YouTube   ─► YouTube Data API v3
      ├── Instagram ─► Apify instagram-scraper
      ├── Facebook  ─► Apify facebook-videos-scraper
      └── Threads   ─► Apify threads-scraper
              │
              ▼
[ UniversalContentModel ] ◄── cross-platform cleaning & normalization
              │
              ▼
[ Streamlit UI ]  /  [ LLM report agent ]  /  [ LINE push ]  /  [ Supabase store ]
```

## Tech Stack

`Python` · `Streamlit` · `pandas` · `Plotly` · `YouTube Data API v3` · `Apify` · `OpenRouter (LLM)` · `APScheduler` · `Supabase` · `pytest`

## Getting Started

### Prerequisites

- Python 3.12 or 3.13 recommended (a virtualenv is advised).
- API keys for the services you want to use (see [Environment variables](#environment-variables)).

### Install

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env             # then fill in your keys
```

### Run

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501`.

> Note: the UI, tabs, language switch, and card layouts are fully browsable without any keys. Live fetching requires the relevant keys below.

## Environment Variables

Copy `.env.example` to `.env` and fill in what you need:

| Variable | Purpose | Required for |
| --- | --- | --- |
| `YOUTUBE_API_KEY` | YouTube Data API v3 | YouTube fetching |
| `APIFY_API_TOKEN` | Apify actors | Instagram / Facebook / Threads fetching |
| `APIFY_*_ACTOR` | Override actor ids | optional (sensible defaults) |
| `OPENROUTER_API_KEY` / `OPENROUTER_MODEL` | LLM report generation | AI reports |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Messaging API | LINE push (optional) |
| `SUPABASE_URL` / `SUPABASE_KEY` | History knowledge base | optional (local JSONL fallback) |

`.env` is gitignored and never committed.

## Project Structure

```
app.py              # Streamlit UI: tabs, i18n, cards, charts, scheduler
data_router.py      # Parallel routing across platforms → UniversalContentModel
content_model.py    # UniversalContentModel + parsing helpers
youtube_service.py  # YouTube Data API v3 (two-stage fetch, Shorts filter)
apify_service.py    # Apify actors for IG / FB / Threads + defensive transforms
llm_agent.py        # DataFrame → prompt → streamed Markdown report (OpenRouter)
line_service.py     # LINE broadcast with 5000-char chunking
db_service.py       # Supabase persistence + local JSONL/Markdown fallback
keywords.csv        # Default keyword presets (editable)
tests/              # pytest suite (unit + Streamlit AppTest)
```

## Testing

```bash
pip install -r requirements-dev.txt
pytest
```

24 tests cover the data model, Apify transforms, router sorting/error isolation, LLM prompt assembly, and an end-to-end Streamlit `AppTest` smoke (bilingual rendering + cross-platform card rendering). Key regressions (duplicate widget ids in English mode, `NaN` title handling, none-view sorting) are locked down by tests.

## Notes

- Apify actor input schemas are defensive defaults; the Facebook keyword-search path in particular may need tuning to the specific actor you use.
- LLM reports are generated in Traditional Chinese regardless of UI language.

---
name: project-scaffold
description: Scaffolding state of the mypocket-app project — what was done, what remains, and next steps per the MYPOCKET.md roadmap
metadata:
  type: project
---

Scaffold + seed + infra completed June 2026.

**What exists:**
- `.venv/` with core deps including `anthropic`, `python-telegram-bot`
- `requirements.txt`, `requirements-dev.txt`, `.env.example`, `.env` (local dev, gitignored)
- Full `app/` package tree — all `__init__.py` stubs present
- 11 SQLAlchemy ORM models fully implemented
- Alembic initial migration applied (`mypocket.db` created, all 11 tables)
- `scripts/seed_categories.py` — 27 categories seeded (12 top-level + 15 children)
- `Makefile`, `Dockerfile`, `docker-compose.yml`, `docker-compose.prod.yml`
- `tests/conftest.py` with full fixture set
- `app/main.py` — minimal FastAPI `/health`
- `app/config.py`, `app/database.py`

**Dev bot:** `@mypocketappdevbot` (id: 8600412264) — token in `.env`

**What does NOT exist yet (v1 next steps in order):**
1. Claude API integration (`app/integrations/anthropic/`) — client + prompts + parser
2. Telegram bot middleware (user auth from DB)
3. Telegram `/start` setup wizard + account configuration
4. Unified message router (text/voice/photo entry point)
5. Manual expense logging handler
6. Voice handler (Whisper transcribe → confirm step)
7. Receipt photo handler (Claude vision)
8. Buoni pasto batch + balance handlers
9. Cash expense logging handler
10. `/report` monthly summary handler
11. Basic Web UI (dashboard + transaction list)

**Why:** Stopped after infra — next session starts with Claude integration layer.

**How to apply:** When continuing, start with `app/integrations/anthropic/client.py` then `prompts.py` then `parser.py`, then wire the bot middleware.

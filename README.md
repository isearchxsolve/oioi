# oioi — AI Animation Canvas

An open-source AI animation canvas: create animations with words on an infinite canvas.
A 7-agent film pipeline turns an idea into script → storyboard images → narration →
Ken-Burns clips → a stitched film, while a provider registry keeps it working with
zero API keys.

## What it is

- **Infinite canvas** — the hero surface; panels recede, content dominates.
- **7-agent film pipeline** — idea → script → storyboard → narration → clips → stitch.
- **Keyless-by-default** — usable with zero API keys (keyless image fallback); users
  can bring their own free keys to unlock higher quality.
- **Multi-provider failover** — `ProviderRegistry` routes chat/image/video/embedding
  across OpenRouter, Groq, Gemini, Cloudflare, Cerebras, Cohere, Pollinations with
  health checks, exponential cooldown, and priority ordering.
- **Concurrency visible** — multiple generations run in parallel; the UI shows live
  queue and progress without blocking the canvas.

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js + React + Tailwind (canvas-first, dark pro-tool UI) |
| Backend | FastAPI (Python) — agent contracts, pipeline orchestration |
| API server | Express (Node) — routes + auth |
| Storage | SQLite via Prisma / SQLAlchemy + Alembic migrations |
| Agents | 7-agent pipeline with typed contracts and QA tests |

## Quick start

```bash
# Backend (FastAPI agents + providers)
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend (Next.js canvas)
npm install
npm run dev

# API server (Express)
cd server && npm install && npm start
```

## Tests

```bash
npm test            # jest suites (backend agent contracts use pytest: cd backend && pytest)
cd backend && pytest
```

## Design principles

Canvas-first · dark, focused pro-tool · concurrency visible · keyless-by-default ·
WCAG AA accessible · responsive (drawers ≤1024px).

## Repository layout

```
backend/        FastAPI: provider registry, agent pipeline, contracts, Alembic
frontend/       Next.js canvas UI
server/         Express API server
film-kit-studio Film pipeline runtime
docs/           Design and delivery documents
```

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Kunal Das.
# OutreachHub

Find part-time, contract and remote AI engineering opportunities from as many legitimate sources
as possible, and contact 30-40 relevant people or companies per day with personalized messages
that **you approve one by one**.

- Web app: FastAPI + SQLite (Postgres-ready) backend, Next.js frontend
- Chrome extension (Manifest V3): assisted manual mode only, starts in step 7
- Docs: [USER_MANUAL.md](./USER_MANUAL.md) (also rendered in-app at `/help`)

> Build order is staged: each step is demoed and approved before the next one starts.
> See **Build status** in [USER_MANUAL.md](./USER_MANUAL.md) for what works today.

## Quick start (Docker)

```bash
cp .env.example .env         # then edit APP_SECRET and any API keys
docker compose up --build
```

- App: http://localhost:3000 — create your login on first visit
- API: http://localhost:8000 (docs at `/docs`, health at `/api/health`)

## Quick start (local, no Docker)

Backend (Python 3.11+):

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows: .venv\Scripts\activate ; macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Frontend (Node 20+):

```bash
cd frontend
npm install
npm run dev                   # http://localhost:3000
```

Set `NEXT_PUBLIC_API_URL=http://localhost:8000` if your API is not on port 8000.

## Required API keys (all in `.env`)

| Key | Needed for | Required from |
| --- | --- | --- |
| `APP_SECRET` | Login session signing | Now (any long random string) |
| `ANTHROPIC_API_KEY` | Scoring and drafting (default LLM provider) | Step 4 |
| `GOOGLE_OAUTH_CLIENT_ID` / `_SECRET` | Gmail send + reply detection (OAuth, desktop app credentials) | Step 5 |
| `BRAVE_API_KEY` or `SERPAPI_KEY` | Search-dork collector | Step 8 |
| `REDDIT_CLIENT_ID` / `_SECRET` | Reddit official API collector | Step 8 |

Everything else runs without keys. No password is ever stored or requested for LinkedIn, X,
Wellfound or Gmail.

## Tests

```bash
cd backend && python -m pytest        # API, auth, profile, onboarding
cd frontend && npm run build          # typecheck + build
```

## Compliance note — what is automated and what is manual

**Automated (official APIs, RSS feeds, public pages, respecting robots.txt and rate limits):**
RemoteOK, We Work Remotely, Remotive, Himalayas, Jobicy, Arbeitnow, Working Nomads, JustRemote,
Remote.co, ai-jobs.net, Lever/Greenhouse/Ashby/Workable/SmartRecruiters/Recruitee public boards,
Upwork and Freelancer public feeds, Hacker News (Algolia API), Reddit (official API), Dev.to,
Hashnode, Lobsters, Product Hunt, GitHub, Hugging Face, YC public directory, funding-news RSS
feeds, search-dork APIs (Brave/SerpAPI/Bing), and Gmail job-alert parsing (read-only OAuth).

**Never automated — manual only, on pages you open yourself:**
LinkedIn, X/Twitter, Wellfound, and any site behind a login. The Chrome extension captures the
visible content of a page *you* opened and fills a draft into a message box *you* will send;
you read it, press Send yourself, and confirm. No scraping, no auto-navigation, no clicking, no
scrolling, no bulk extraction, no background pages, no stored credentials.

**Contact data:** only publicly listed contact details from public pages. No guessing, no
enrichment of hidden data, nothing behind logins. Suppression list and opt-outs are honored
everywhere.

## Repository layout

```
backend/     FastAPI app, SQLAlchemy models, Alembic migrations, collectors (step 2+), tests
frontend/    Next.js app: Dashboard, Profile, Review Queue (step 5), ...
extension/   Chrome Manifest V3 extension (step 7)
config/      YAML config for collectors and search dorks (step 2+)
docs/        Extra documentation
USER_MANUAL.md   The manual (rendered in-app at /help)
docker-compose.yml   One-command local run
```

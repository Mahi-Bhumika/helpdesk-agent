
# HIKA — Helpdesk Intelligence & Knowledge Automation

A multi-tenant SaaS platform that lets any business upload their own documents/FAQs and embed an AI-powered support chatbot on their website — answering visitor questions using **only that business's own content**, with strict per-tenant data isolation enforced at the database level.

Built as a two-person, seven-week project : a Next.js dashboard, a FastAPI + RAG backend, a standalone embeddable widget, and a containerized CI/CD pipeline taking it from "runs on my machine" to a real, gated, auto-deploying production system.

---

## Table of contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Getting started](#getting-started)
- [Environment variables](#environment-variables)
- [Database schema](#database-schema)
- [API reference](#api-reference)
- [Security model](#security-model)
- [The RAG pipeline](#the-rag-pipeline)
- [Embedding the widget](#embedding-the-widget)
- [CI/CD pipeline](#cicd-pipeline)
- [Deployment](#deployment)
- [Known limitations / roadmap](#known-limitations--roadmap)
- [Contributors](#contributors)

---

## Overview

Two audiences use the system:

- **Tenant staff** (owners + invited members) — sign up, upload documents, configure the bot's name/greeting/theme, view analytics and chat transcripts, manage their team, via a dashboard.
- **End visitors** — the public, who chat with a bubble widget embedded on the tenant's own website. The bot answers strictly from that tenant's uploaded documents, or says it doesn't know — it never blends in outside knowledge or another tenant's data.

The core technical bet is **Retrieval-Augmented Generation (RAG)**: uploaded PDFs are parsed, chunked, and embedded into vectors; a visitor's question is embedded the same way and matched against those vectors; the closest matching chunks are handed to an LLM along with a system prompt that keeps its answer grounded in what was actually retrieved.

---

## Architecture

```
┌─────────────────┐         ┌──────────────────┐         ┌────────────────────┐
│  Next.js         │  HTTPS  │  FastAPI          │  asyncpg │  Supabase Postgres │
│  Dashboard        │───────▶│  (Docker, Render) │────────▶│  + pgvector         │
│  (Vercel)         │  JWT    │                   │          │  + Row-Level        │
└─────────────────┘         │  /tenants          │          │    Security         │
                              │  /documents        │          └────────────────────┘
┌─────────────────┐         │  /kb/upload        │
│  widget.js        │  HTTPS  │  /chat             │
│  (embedded on any │────────▶│  /chat/end         │───────▶  Groq (LLM inference)
│  tenant website)  │  Origin │  /sessions         │
└─────────────────┘  check   │  /admin/*          │
                              │  /invite/accept     │
                              └──────────────────┘
```

Two genuinely separate traffic paths hit the backend, each with its own protection model:

1. **Dashboard → FastAPI**: authenticated tenant staff, protected by JWT verification (`Authorization: Bearer <token>`) checked against Supabase's public signing keys.
2. **Widget → FastAPI**: anonymous end visitors, no login. Protected instead by a per-tenant `website_domain` check against the request's `Origin` header, plus rate limiting.

Both paths converge on the same tenant-scoped Postgres tables, with Row-Level Security enforcing isolation as a second, independent layer beneath the application code.

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Next.js (App Router), TypeScript, Tailwind CSS, Recharts |
| Backend | FastAPI, SQLAlchemy (async) + asyncpg, Pydantic |
| Database | Supabase (Postgres 16 + `pgvector`), Row-Level Security |
| Auth | Supabase Auth — JWT, ES256 / JWKS (asymmetric, not shared-secret) |
| Embeddings | `onnxruntime` + `Xenova/all-MiniLM-L6-v2` (384-dim, local, free) |
| LLM | Groq (`openai/gpt-oss-20b`) |
| PDF parsing | `pdfplumber` (primary), `PyPDF2` (fallback) |
| Containerization | Docker, `docker-compose` (local dev parity) |
| CI/CD | GitHub Actions, branch protection with required status checks |
| Hosting | Render (backend, Docker), Vercel (frontend) |
| Widget hosting | Vercel `public/` + GitHub Pages (test/demo) |

---

## Project structure

```
helpdesk-agent/
├── .github/
│   └── workflows/
│       ├── backend.yml        # lint (ruff) + smoke tests + Docker build sanity check
│       └── frontend.yml       # lint (eslint) + build
├── backend/
│   ├── main.py                 # all FastAPI routes
│   ├── auth.py                 # decode_jwt / get_current_user, JWKS verification
│   ├── database.py             # async engine + get_db() dependency
│   ├── extract_text.py         # PDF → raw text
│   ├── chunking.py              # text → token-exact chunks → ONNX embeddings
│   ├── rate_limit.py            # sliding-window rate limiter
│   ├── schema.sql               # full CREATE TABLE / index / constraint set
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   └── tests/
│       └── test_smoke.py        # /health, /tenants, /chat smoke tests
├── frontend/
│   ├── app/
│   │   ├── (public)/            # landing page, login, signup, pending, declined
│   │   └── dashboard/           # analytics, documents, sessions, settings, invites, member
│   ├── lib/
│   │   ├── supabase.ts
│   │   ├── auth-context.tsx
│   │   └── api.ts               # authedFetch() helper
│   ├── components/
│   └── public/
│       └── widget.js            # standalone embeddable widget, Shadow DOM isolated
├── docker-compose.yml            # FastAPI + local pgvector-enabled Postgres
└── README.md
```

---

## Getting started

### Prerequisites

- Node.js + npm
- Python 3.13
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (with WSL2 on Windows)
- A Supabase project (Postgres + Auth)
- A free [Groq](https://console.groq.com/) API key

### Local setup

```bash
git clone <repo-url>
cd helpdesk-agent
```

**Backend — via Docker Compose (recommended, matches CI/production):**

```bash
# backend/.env.docker — local-only, gitignored
echo "GROQ_API_KEY=your_key_here" > backend/.env.docker

docker-compose up --build
```

This starts FastAPI on `:8000` and a local `pgvector`-enabled Postgres on `:5432`, seeded automatically from `backend/schema.sql`. `DATABASE_URL` for this environment is set inside `docker-compose.yml` itself — it points at the local container, **never** at production Supabase.

Verify:
```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

Create `frontend/.env.local` with the variables listed below, then visit `http://localhost:3000`.

---

## Environment variables

Four separate places these need to exist, and they are **not** all the same values:

| Variable | Where it's used | Notes |
|---|---|---|
| `DATABASE_URL` | Backend | Supabase **pooler** connection string in prod/CI (port `6543`), local Postgres container in `docker-compose` |
| `GROQ_API_KEY` | Backend | Real secret everywhere |
| `SUPABASE_URL` | Backend | Bare project URL (`https://xxxx.supabase.co`) — `auth.py` derives the JWKS endpoint from this itself |
| `NEXT_PUBLIC_SUPABASE_URL` | Frontend | Same Supabase project, public by design |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Frontend | Public anon key — protected by RLS, not secrecy |
| `NEXT_PUBLIC_API_URL` | Frontend | The backend's base URL |

A `.env.example` at the repo root documents every required key as a placeholder. Real values live in `backend/.env` (local, gitignored), `backend/.env.docker` (local Docker only, gitignored), Render's Environment tab (production backend), and Vercel's Environment Variables (production frontend) — never in a committed file.

---

## Database schema

8 tables, all tenant-scoped via a denormalized `tenant_id` (duplicated onto high-volume child tables deliberately, to keep RLS policies simple and fast):

| Table | Purpose |
|---|---|
| `tenants` | One row per business — name, bot config, `website_domain`, `invite_token` |
| `users` | Individual logins — `role` (owner/member), `status` (pending/active/declined) |
| `documents` | Uploaded file metadata + ingestion `status` lifecycle |
| `document_chunks` | Parsed, chunked, embedded (`vector(384)`) pieces of each document |
| `end_users` | Anonymous-by-default website visitors |
| `chat_sessions` | One per widget conversation — CSAT rating, start/end timestamps |
| `messages` | Every question and answer, with response latency |
| `message_sources` | Which chunks a given bot answer cited, with relevance scores |

Primary keys are UUIDs throughout (unguessable, standard for multi-tenant SaaS). Row-Level Security is enabled on every table with real policies — "enabled with zero policies" is a deliberate, audited state nowhere in this schema; it would silently deny access to everyone, including a table's rightful owner.

---

## API reference

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /health` | none | Liveness check |
| `POST /tenants` | JWT (identity-only) | Create a tenant on first login |
| `POST /invite/accept` | JWT (identity-only) | Link an invited user to a tenant |
| `GET/POST/PUT /documents` | JWT | Manage uploaded documents |
| `POST /kb/upload` | JWT | Full ingest pipeline: parse → chunk → embed → store |
| `GET /tenants/{id}/widget-config` | none (rate-limited) | Public bot config for the widget on load |
| `POST /chat` | Origin check | Retrieval + generation; anonymous visitors |
| `POST /chat/end` | Origin check | Closes a session, records CSAT |
| `GET /sessions`, `GET /sessions/{id}/messages` | JWT | Tenant-scoped chat history |
| `GET /admin/pending-users`, `POST /admin/approve-user`, `POST /admin/decline-user` | JWT (owner-only) | Invite approval queue |

Auto-generated interactive docs are available at `/docs` on any running instance.

---

## Security model

- **Tenant isolation, two independent layers**: application-level `WHERE tenant_id = ...` scoping *and* database-level RLS policies underneath it, so a bug in one doesn't expose the other's failure.
- **JWT verification uses JWKS (ES256)**, not a shared secret — Supabase's actual signing scheme, fetched and cached via `PyJWKClient`.
- **`/chat` and `/chat/end` use an Origin check, not JWT** — visitors don't log in, so authorization instead compares the real `Origin` header against the tenant's registered `website_domain`, both normalized to `scheme://host` before an exact match (a raw substring check was found and fixed as a real spoofing gap).
- **Rate limiting** on both `/chat` and `/tenants/{id}/widget-config`, on separate keys, so normal page browsing never eats into a visitor's chat quota.
- **CORS is deliberately permissive** (`allow_origins=["*"]`) — this is a conscious tradeoff, not an oversight: CORS only controls whether a browser lets JavaScript *read* a response, and every route that actually matters is independently protected by JWT or the Origin check above.
- A repeatable cross-tenant attack script exercises both traffic paths (direct-Supabase and FastAPI) against every tenant-scoped table, including a self-read control that distinguishes real isolation from a table that's simply locked out for everyone.

---

## The RAG pipeline

```
PDF upload
   → extract_text()        pdfplumber, page by page
   → chunk_text()           token-exact chunking (250 tokens / 40 overlap),
                              using the embedding model's own tokenizer
   → embed_chunks()          ONNX runtime + MiniLM, batched, L2-normalized
   → stored in document_chunks (pgvector)

Visitor question
   → embedded the same way as chunks (same model, same normalization)
   → pgvector similarity search, tenant-scoped, top_k nearest chunks
   → chunks + system prompt + question → Groq LLM
   → grounded answer, or an honest "I don't know" if nothing relevant was found
```

Embeddings run on `onnxruntime` rather than `sentence-transformers`/`torch` specifically to fit Render's free-tier memory limit — inference-only, no training capability needed, dramatically smaller footprint for the identical output.

---

## Embedding the widget

From a tenant's dashboard, the Embed Script page generates a snippet like:

```html
<script src="https://your-widget-host/widget.js" data-tenant-id="..."></script>
```

`widget.js` is a single, dependency-free, Shadow-DOM-isolated file — no framework, no build step required on the tenant's side. It fetches live bot settings (name, greeting, theme color) from `/tenants/{id}/widget-config` on every page load, so updating a tenant's bot settings takes effect immediately without regenerating the embed snippet.

---

## CI/CD pipeline

```
push / PR → GitHub Actions
              ├── backend.yml:  ruff lint → Docker build sanity check →
              │                  boot uvicorn → pytest smoke tests
              │                  (real Supabase data, real tenant, read-only)
              └── frontend.yml: eslint → next build
                     │
                     ▼
         Both required as passing status checks on `main`
         (branch protection: no direct pushes, no bypassing, even for admins)
                     │
                     ▼
         Render: Auto-Deploy = "After CI Checks Pass" (backend)
         Vercel: auto-deploys on merge to main (frontend)
```

The Docker image built and tested in CI is the same image that runs in production — the Dockerfile's Python version, dependencies, and entrypoint are identical across a local machine, `docker-compose`, CI, and Render.

---

## Deployment

- **Backend** — Render, building directly from `backend/Dockerfile` (not buildpacks), deploying only once GitHub Actions' checks pass.
- **Frontend** — Vercel, auto-deploying `main` on every merge.
- **Widget** — a static file served from Vercel's `public/` folder (and mirrored to GitHub Pages for the demo test page); tenant sites load it via `<script src>`, so redeploying it updates every embedded instance with zero action from any tenant.

---

## Known limitations / roadmap

- `GET /sessions` is capped at 100 rows with no pagination yet.
- Declining an invited user is one-way by design — no re-invite/reversal flow.
- No UI yet surfaces a tenant's `invite_token` as a copyable link (the token exists in the schema; nothing generates the shareable URL from it).

---

## Contributors

Built by **Mahi** (backend, RAG pipeline, security/auth, Docker/CI-CD) and **Bhumika** (frontend dashboard, embeddable widget, CI/CD verification) over a seven-week sprint, from an empty repository to a live, multi-tenant, CI/CD-deployed product.

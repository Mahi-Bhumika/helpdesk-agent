# Helpdesk Agent (Bot AI)

A multi-tenant SaaS platform where companies sign up, upload their own documents/FAQs, and get an AI-powered chat widget they can embed on their own website. The widget answers visitor questions using **only that company's own uploaded content** — with strict per-tenant data isolation enforced at the database level.

Built as a two-person college project. Backend/RLS/Auth by Person A, frontend/end-to-end wiring/QA by Person B (Bhumika).

---

## What it does

- A company signs up, configures a bot (name, greeting, theme), and uploads PDFs/FAQs
- The company pastes a small embed script into their own website
- Visitors on that website chat with the bot; the bot answers using Retrieval-Augmented Generation (RAG) over that company's documents only
- The company's dashboard shows chat history, analytics, and lets them manage documents and teammates
- Teammates join via an invite link and require **owner approval** before getting access

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, SQLAlchemy (async) + asyncpg |
| Database | Supabase (managed Postgres) + `pgvector` extension |
| Auth | Supabase Auth (JWT-based sessions) |
| Embeddings | `onnxruntime` running a pre-converted `all-MiniLM-L6-v2` (384-dim), batched inference |
| PDF parsing | `pdfplumber` |
| LLM generation | Groq (`openai/gpt-oss-20b`), OpenAI's open-weight model served on Groq's inference hardware |
| Frontend | Next.js (App Router), TypeScript, Tailwind CSS |
| File upload | `react-dropzone` |
| Backend hosting | Render |
| Frontend hosting | Vercel |
| Security | Postgres Row-Level Security (RLS), tenant isolation via `tenant_id` |

---

## Architecture

**Ingestion (`/kb/upload`)**
```
PDF upload → pdfplumber (extract text) → tokenizer-based chunking
  (250 tokens, 40 overlap, short trailing chunks merged)
  → ONNX/MiniLM embeddings (384-dim, batched, L2-normalized)
  → stored in document_chunks (pgvector), tenant_id attached
```

**Retrieval + generation (`/chat`)**
```
User question → embedded with the same model/pooling as ingestion
  → pgvector similarity search (Euclidean `<->`, tenant-scoped)
  → top_k chunks assembled into context
  → sent to Groq with a grounding system prompt
  → answer returned + session/messages/message_sources logged
```

**Multi-tenancy**
Every tenant-scoped table (`documents`, `document_chunks`, `chat_sessions`, `messages`) carries a denormalized `tenant_id` column — duplicated rather than derived via joins, so Row-Level Security policies can filter with a simple `WHERE tenant_id = ...` instead of a multi-table join. This is a deliberate tradeoff: slightly more write complexity in exchange for simpler, faster, harder-to-get-wrong security policies.

---

## Database schema

| Table | Purpose |
|---|---|
| `tenants` | One row per company. Bot config (name, greeting, theme), permanent `invite_token` |
| `users` | Individual logins. `role` (owner/member), `status` (pending/active), tenant link |
| `documents` | Uploaded source files, lifecycle status (`uploaded` → `ready`) |
| `document_chunks` | Chunked + embedded text (`vector(384)`), tenant-scoped |
| `end_users` | Anonymous-by-default website visitors (nullable identity) |
| `chat_sessions` | One row per widget conversation |
| `messages` | Individual messages within a session |
| `message_sources` | Which chunks contributed to a given bot answer, with a relevance score |

All primary keys are UUIDs (not auto-incrementing integers) so IDs can't be probed/guessed.

---

## Security model

- **Row-Level Security (RLS)** is enabled on every tenant-scoped table. Policies check both `tenant_id` match *and* `users.status = 'active'`, so a pending (unapproved) user cannot read tenant data even though their JWT is valid and correctly tenant-linked.
- **Invite flow**: a single permanent, unguessable link per tenant (`tenants.invite_token`). Anyone with the link can request to join, but lands as `status = 'pending'` and sees a waiting screen until the tenant owner explicitly approves or declines them from the dashboard.
- **Tenant isolation is enforced at the database layer**, not just in application code — proven via a deliberate "attack script" that attempts cross-tenant reads and confirms they fail.
- Real secrets (`DATABASE_URL`, `GROQ_API_KEY`, Supabase keys) live only in `.env` (gitignored) locally and each platform's own environment variable settings in production — never committed.

---

## Project structure

```
helpdesk-agent/
├── backend/
│   ├── main.py            # FastAPI routes: /tenants, /documents, /kb/upload, /chat, /admin/*
│   ├── database.py        # Async SQLAlchemy engine + get_db() dependency
│   ├── extract_text.py    # PDF → raw text
│   ├── chunking.py        # chunk_text(), embed_chunks() (ONNX/MiniLM, batched)
│   ├── requirements.txt
│   └── .env               # DATABASE_URL, GROQ_API_KEY (gitignored)
├── frontend/
│   ├── app/
│   │   ├── signup/, login/, pending-approval/
│   │   └── dashboard/     # analytics, documents, settings, embed, admin/invites
│   ├── lib/
│   │   ├── supabase.ts
│   │   └── auth-context.tsx
│   └── .env.local
├── .env.example
├── .gitignore
└── README.md
```

---

## Local setup

**Backend**
```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows; use `source venv/bin/activate` on Mac/Linux
python -m pip install -r requirements.txt
# create .env with DATABASE_URL and GROQ_API_KEY (see .env.example)
uvicorn main:app --reload
```
Visit `http://localhost:8000/docs` for the interactive API explorer.

**Frontend**
```bash
cd frontend
npm install
# create .env.local with NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY
npm run dev
```

**Database**
Schema is managed via Supabase's SQL Editor. `CREATE TABLE` statements, RLS policies, and any `ALTER TABLE` fixes should be kept in `backend/schema.sql` for version control (not just left in Supabase's dashboard history).

---

## Status by week

- **Week 1** — FastAPI + Postgres foundations. Schema designed and deployed (8 tables), first live endpoint (`POST /tenants`), backend deployed to Render.
- **Week 2** — Full RAG pipeline: PDF parsing, chunking, embeddings (migrated from `sentence-transformers`/`torch` to `onnxruntime` to fit Render's free-tier memory limit), pgvector retrieval, Groq generation. `/kb/upload` hardened against event-loop blocking and batch-size memory issues.
- **Week 3** — Full Next.js dashboard: Supabase auth, protected routes, document upload UI, analytics, bot settings, embed script generator. `/chat` upgraded to persist real session/message/source data. First RLS policies written (`chat_sessions`, `messages`).
- **Week 4 (in progress)** — Full RLS hardening across all remaining tables (`documents`, `document_chunks`, `tenants`, `users`), each requiring both tenant match and active-user status. Building the owner-approval invite flow (pending → active) that replaces the originally-planned Stripe billing integration.
- **Week 5 (planned)** — Dockerize the backend, `docker-compose` for local dev parity, GitHub Actions CI/CD auto-deploying to Render and Vercel on merge to `main`.

---

## Deliberate scope decisions

- **Billing/subscriptions**: dropped from scope. Originally planned as a Week 4 Stripe integration; judged not meaningful for a college demo with no real tenants or payments. Unused placeholder columns remain on `tenants` from Week 1 but aren't wired up.
- **Owner approval for invites**: originally skipped in Week 1 (judged disproportionate given the actual risk — a support bot over already-public documents), later reversed in Week 4 in favor of the original blueprint's approval flow, since it's a stronger, more relevant thing to demo than billing.
- **Local embeddings over API-based ones**: chosen to keep the project free-to-run and self-contained, with no billing infrastructure required to prove the pipeline.
- **Vector similarity indexing (`ivfflat`/`hnsw`)**: deferred until real data volume exists to tune against.

---

## Known limitations

- No rate limiting or abuse protection on `/chat` yet
- Multi-column PDF layouts are not specially handled (assumes mostly single-column source documents)
- No revocation mechanism for a compromised invite link beyond manually rotating `tenants.invite_token`
- Embedding model is uncased and can produce `[UNK]` tokens on rare characters — acceptable for retrieval, will matter if raw chunk text is ever shown to users as a citation

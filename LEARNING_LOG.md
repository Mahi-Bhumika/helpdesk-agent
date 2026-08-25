# LEARNING LOG
Week 1 — Learning Log (Bhumika)
 
Went from "install Node" on Day 1 to a live, deployed, end-to-end working app by Day 7 — Vercel frontend → Render backend → Supabase Postgres, real tenant rows landing in a real database, over the actual internet, not just localhost. Also survived a three-layer production bug in one sitting (typo → CORS → server crash) and came out the other side understanding why each layer failed, not just that it did.
 
What got built this week
Next.js app scaffolded (TypeScript, Tailwind, App Router), deployed live on Vercel
Repo structured as a monorepo (frontend/ + backend/), fully synced with partner's FastAPI work
ER diagram locked for all 6 core tables: users, tenants, documents, document_chunks, chat_sessions, messages
A real working feature: a form that POSTs to a live FastAPI /tenants endpoint, which writes to a real Supabase Postgres table — confirmed both via the API response and by checking the row directly in Supabase's table editor
GitHub Issues opened for all of Phase 2 (Week 2 — chunking, embeddings, RAG loop), split by owner
First real experience with gh CLI for repo management from the terminal
Concepts learned (the real list)
Git fundamentals: working directory → staging → commit → push, git add -A vs git commit -a, resolving merge conflicts, reading git errors instead of panicking
Next.js App Router basics: Server Components vs Client Components, fetch/useEffect for client-side data fetching, when each pattern actually applies
Environment variables done right: .env vs .env.example, why secrets are gitignored, why NEXT_PUBLIC_ variables are intentionally not secret, and that Vercel's env vars are a separate dashboard config — not read from any local file
localhost actually means "this machine" — cross-device testing doesn't work until something's deployed with a real public URL
CORS, hands-on: what a preflight (OPTIONS) request is, why "blocked by CORS" can sometimes be a red herring for a different underlying server crash, and how to isolate that with a direct header check
Debugging with real tools instead of guessing: browser DevTools console, Invoke-WebRequest as a PowerShell equivalent to curl, and Render's Logs tab for server-side tracebacks
GitHub Issues as a lightweight project-tracking layer, created both via UI and via gh issue create
The debugging saga (worth remembering, not just logging)
 
day 7's flow was a genuinely good case study in layered failure:
 
Trailing-slash typo in NEXT_PUBLIC_API_URL → cosmetic, not the real blocker
CORS block → real, but looked the same in the console the whole time, even after two separate fixes, because of a subtle mismatch (production URL vs. auto-generated preview URL)
500 Internal Server Error masquerading as a CORS error → the actual final bug; when FastAPI crashes on an unhandled exception, it can fail to attach CORS headers to that response, so the browser reports it as a CORS failure even though CORS itself was already correctly configured
 
The lesson that's worth keeping, not just the fix: the error message you see first isn't always the error that's actually happening. Verifying each layer independently (manual header check before assuming "still CORS") is what actually cracked it, instead of re-fixing the same thing repeatedly.
 
What confused you (per the ask-yourself-honestly section)
Initially assumed "failed to fetch" and a CORS error were the same thing — they're not; CORS gives a specific browser message, "failed to fetch" is more generic
Didn't immediately realize Vercel gives multiple URLs (production vs. git-branch preview deploys) with different origins — cost real time until caught via the console's exact origin string
.env.local vs .env.example vs Vercel's dashboard env vars — three different places holding "the same kind of thing," easy to conflate before it clicked that only one of them is shared



# Learning Log — Week 1 (Mahi)

## What I actually built this week
- A FastAPI backend, from an empty folder to a deployed, publicly reachable service on Render
- A real Postgres database on Supabase, schema-complete across 8 tables, with pgvector enabled for next week
- A working `POST /tenants` endpoint that takes a request from a browser and persists a real row in production
- Full end-to-end proof that four separate systems (browser → Next.js → FastAPI → Postgres) can talk to each other across local dev and live deployment

## New concepts I understand now (that I didn't Monday)
- **Virtual environments** — not an app, just an isolated folder holding a private copy of Python + packages, so projects don't fight over versions
- **REST semantics** — verbs (GET/POST/PUT) are actions, URLs are nouns; status codes communicate outcome (200 success, 404 not found, 422 validation failure)
- **Pydantic models** — define the *shape* data must have; FastAPI rejects malformed requests automatically, before my own code even runs
- **Primary keys vs foreign keys** — a table's unique identifier, and a column in another table that points to it; this is the entire mechanism behind how relational data connects
- **Multi-tenancy** — one platform, many businesses, strict data isolation between them; `tenant_id` is the thread that ties every table back to "which business does this belong to"
- **Row-Level Security (RLS)** — a database-level enforcement of tenant isolation, so a bug in application code can't leak one tenant's data to another; security lives at the data layer, not just the app layer
- **Denormalization as a deliberate tradeoff** — duplicating `tenant_id` onto child tables (`messages`, `document_chunks`) instead of always deriving it via joins, specifically to keep security policies simple and fast on high-volume tables
- **CORS** — browsers block cross-origin requests by default; the backend has to explicitly allow which frontend origins can call it
- **The difference between a connection string and an endpoint** — one is a private credential for my backend to reach the database directly; the other is a public URL the frontend calls. Conflating these is a real security mistake I almost made.
- **IPv6 vs IPv4 connectivity in deployment** — a connection that works locally can fail in production for infrastructure reasons that have nothing to do with my code (Render couldn't reach Supabase's direct/IPv6 host; the pooled/IPv4 endpoint fixed it)

## Real bugs I hit, diagnosed, and fixed myself
1. **Duplicate `FastAPI()` app instance** — pasted a code snippet's placeholder comments as if they were real code, silently creating a second `app` object that overwrote my first one and erased all my routes except the newest addition. Root cause wasn't the code itself, it was misreading what a snippet's context comments meant.
2. **Production-only crash: `OSError: Network is unreachable`** — worked perfectly locally, broke in Render. Traced it through actual server logs (not guesswork) to Supabase's direct connection string resolving to an IPv6 address Render couldn't route to; fixed by switching to the connection pooler.
3. **Folder/file locking on Windows** — renames failing because VS Code still had a handle on the folder; learned to close the workspace before renaming, not just `cd` away from it.
4. **Wrong Python interpreter selected in VS Code** — Pylance was checking against global Python instead of my venv, producing false "not defined" warnings that looked like real bugs but weren't.

## Decisions I made deliberately, not by default
- **Chose invite links over an owner-approval queue** for team member onboarding — traced through the actual threat model (a support chatbot over already-public documents) and concluded the extra approval-flow complexity wasn't proportionate to the real risk. Matching security investment to actual stakes, rather than defaulting to "more security is always better."
- **Chose a single permanent invite token on the tenant**, not a per-invite table with expiry — simpler, and sufficient for what the product actually needs right now. Know how to extend it later (regenerate token to revoke) if requirements change.
- **Denormalized `tenant_id` onto `messages` and `document_chunks`** — a conscious tradeoff (write complexity for read speed and simpler RLS policies), not something I did by accident or without understanding the cost.

## What I'd do differently next time
- Rotate any credential immediately the moment it's exposed anywhere it shouldn't be — don't let "I'll do it later" happen even once.
- When copy-pasting instructions that include comments like `# ... existing code`, stop and actually read what the comment means before pasting — it's telling me where something goes, not what to type.
- Test against the *same* connection method locally and in production (pooled, not direct) from the start, rather than discovering the mismatch only after a production-only failure.

## Heading into Week 2
Foundations are solid: live backend, live database, schema locked and implemented, full request chain proven end-to-end. Next week moves into the actual product logic — parsing documents, chunking them, generating embeddings, and building real retrieval into a working single-tenant RAG chatbot.


# Helpdesk Agent — Week 2 Learning Log - Mahi


## Day 8 (Mon) — PDF parsing

- Installed `pdfplumber` (primary) + `PyPDF2` (fallback) for PDF text extraction
- Built `extract_text()` — opens a PDF, extracts text page by page, skips pages with no extractable text (image-only/scanned) with a warning instead of crashing on `None`
- **Known limitation, deliberately deferred**: naive extraction can silently garble multi-column PDFs (reads across columns instead of down one at a time). Target documents are expected to be mostly single-column, so a real fix (bounding-box column detection) was not built — flagged as a risk to revisit only if it actually shows up in real documents

## Day 9 (Tue) — Chunking + embeddings

- Built `chunk_text()` — overlapping fixed-size chunking by token count
- Built `embed_chunks()` using local `sentence-transformers` (`all-MiniLM-L6-v2`), 384-dim output
- **Bug caught**: original chunk-size plan (300–500 tokens) directly conflicted with MiniLM's real 256-token limit — anything longer gets silently truncated, no error. Corrected to **250 tokens / 40 overlap**, safely under the ceiling
- **Correction made mid-build**: first draft of `chunk_text()` split on whitespace-as-token-proxy; switched to using the model's own tokenizer directly so chunk sizes match what the model actually sees
- **Known limitation, deliberately deferred**: MiniLM's tokenizer is uncased and drops out-of-vocabulary characters (`[UNK]`) — chunk text comes back lowercased with occasional `[UNK]` tokens on decode. Fine for embedding quality; will matter if chunks are ever shown to users as citations (`message_sources` display) — revisit then
- Ran full pipeline (`extract_text` → `chunk_text` → `embed_chunks`) end-to-end on a real 36K-character PDF: 59 chunks, all 384-dim, no crashes

## Day 10 (Wed) — pgvector + schema hardening

- Enabled `pgvector` extension, created `document_chunks` table (`vector(384)` column, `tenant_id` denormalized per the Week 1 multi-tenancy design)
- Ran a full schema cross-check (`information_schema`, `pg_indexes`) prompted by a teammate's checklist
- **Real bug found and fixed**: `tenant_id` was nullable on nearly every table (`chat_sessions`, `document_chunks`, `documents`, `end_users`, `messages`, `users`), despite the entire RLS isolation strategy depending on it always being present. A `NULL` row here would be silently invisible to every RLS policy rather than erroring. Fixed with `ALTER TABLE ... SET NOT NULL` across all affected tables, plus `document_chunks.document_id`/`chunk_index`
- **Real gap found and fixed**: no indexes existed on `tenant_id` anywhere, despite it being the column every query filters on. Added indexes on `tenant_id` for all tenant-scoped tables, plus `messages.session_id` and `document_chunks.document_id`
- Added a `CHECK` constraint on `users.role` (`IN ('owner', 'member')`) since nothing at the DB level was preventing typos in a field that gates permissions
- **Deliberately deferred**: vector similarity index (`ivfflat`) — needs real row count to tune the `lists` parameter properly; revisit when retrieval work starts with real data volume

## Day 11 (Thu) — `/kb/upload` ingestion endpoint

- Upgraded `/documents` (create, read, update) from Day 2's fake in-memory dictionary to real Postgres inserts — this had never been upgraded when `/tenants` got the same treatment back on Day 6
- Built `/kb/upload` — full pipeline behind one endpoint: accepts a PDF via `multipart/form-data`, writes it to a temp file, runs parse → chunk → embed, batch-inserts into `document_chunks`
- Added `documents.status` lifecycle update (`'uploaded'` → `'ready'`) inside the same transaction as the chunk inserts, so status only ever reflects reality
- **Bug**: `.env` had the real `DATABASE_URL` connection string but was missing the `DATABASE_URL=` key prefix — just a bare value on its own line. `os.getenv()` silently returned `None`, crashing `create_async_engine()` at import time
- **Bug**: FastAPI's `File`/`Form` handling requires the separate `python-multipart` package, which isn't bundled — missing it crashed the server at route-registration time with a clear error pointing to the fix
- **Bug (found via UUID vs int mismatch)**: leftover fake-db `GET`/`PUT /documents/{doc_id}` routes still expected an `int` id instead of the real UUID primary key — upgraded to match the real schema

## Day 12 (Fri) — Edge cases & data quality

- Added `min_chunk_size` handling to `chunk_text()` — a trailing chunk smaller than 20 tokens now merges into the previous chunk instead of existing as its own low-signal row
- Audited real stored data directly via SQL rather than trusting the pipeline blindly: confirmed every embedding was 384-dim with no nulls, no duplicate `chunk_text` rows (no repeating headers/footers in this PDF), shortest real chunks were 588+ characters (confirming the `min_chunk_size` fix worked)
- Noted: source PDF content is code-heavy (C++ syntax) — flagged as a factor that could affect retrieval sharpness on code-specific questions, since code has less natural-language structure for a sentence embedding model to key off of

## Day 12.5 — Deployment: Render OOM, switch to ONNX

- First deploy attempt failed: `ModuleNotFoundError: sentence_transformers` — package was in the local venv but never actually added to `requirements.txt`
- After fixing that: `Out of memory (used over 512Mi)` — `torch` + loading MiniLM at import time exceeded Render's free-tier 512MB limit
- **Real fix, not a workaround**: rewrote the entire embedding pipeline to use `onnxruntime` instead of `sentence-transformers`/`torch` — same model (`Xenova/all-MiniLM-L6-v2`, pre-converted ONNX weights), same output quality, none of `torch`'s memory overhead. Implemented tokenization (`AutoTokenizer`), manual mean pooling, and L2 normalization by hand, since the `sentence-transformers` convenience wrapper was no longer available
- Chose this over paying for more RAM or switching to a paid embeddings API, since demonstrating real deployment problem-solving was itself a project goal, and the project doesn't need to survive real production load (college prototype, 1–2 demos)
- **Bug (twice)**: a test snippet (`from chunking import session, embed_chunks`) got left inside `chunking.py` itself instead of a separate test file — caused a circular self-import. Happened once locally, then again after a broken version got committed and deployed
- Deploy succeeded after the fix — confirmed via `Status: Live` and no `Out of memory` message, since Render's free tier doesn't expose a memory graph to check directly

## Day 13 (Sat) — Retrieval

- Built the pgvector similarity search: `ORDER BY embedding <-> :query_embedding LIMIT :top_k`, filtered by `WHERE tenant_id = :tenant_id`
- Built `/chat` (retrieval-only version) — embeds the question the same way chunks were embedded, returns raw matched chunks, no LLM yet, to isolate and prove retrieval quality before adding generation
- **Bug**: `asyncpg.exceptions.DuplicatePreparedStatementError` — Supabase's connection pooler (PgBouncer) doesn't properly support `asyncpg`'s default prepared-statement caching. Fixed with `connect_args={"statement_cache_size": 0}` on the async engine — benefits every endpoint, not just `/chat`
- **Not a bug, a data mismatch**: `/chat` returned zero results on first real test — traced to the `tenant_id` used in the test request not matching the `tenant_id` actually attached to freshly re-uploaded data (after the ONNX migration required clearing `document_chunks`). Confirmed via `SELECT DISTINCT tenant_id FROM document_chunks`
- **Milestone**: tested "What is encapsulation?" — top results correctly surfaced the real definition chunks and a relevant summary-table entry, with cleanly ascending distance values, despite no literal keyword overlap with the question. Confirms genuine semantic search, not keyword matching

## Day 14 (Sun) — Generation

- Integrated Groq (`chat.completions.create`) into `/chat` — retrieved chunks get assembled into a `context` string, combined with a system prompt instructing the model to answer only from that context, sent alongside the user's question
- **Bug**: `NameError: name 'os' is not defined` — `os` had only ever been imported under an alias (`import os as os_module`) from Day 11's `/kb/upload` code; new code assumed the plain name existed. Fixed by adding a plain `import os`
- **Bug**: stray extra closing parenthesis (`Groq(api_key=os_module.getenv("GROQ_API_KEY")))`) — simple copy-paste/edit slip, caught immediately by Python's syntax error pointing at the exact line
- **Bug**: `groq.NotFoundError` — `llama-3.1-8b-instant` doesn't exist on this account's current model list, despite being referenced in multiple docs/tutorials. Resolved by calling `client.models.list()` to get the account's real, live model list rather than trusting external sources. Switched to `openai/gpt-oss-20b`
- **Milestone — full RAG loop working end to end**: "What is encapsulation?" produced a real generated answer, accurate and directly traceable to the retrieved chunks rather than hallucinated from the model's general training knowledge

## Day 14.5 — Production debugging: `/kb/upload` on Render

- `/kb/upload` worked locally, returned a 502 with **no application error logged** on Render — a different failure class than a crash (something upstream, Render's proxy, gave up waiting rather than the app itself dying)
- **Root cause**: the endpoint is `async def` but ran CPU-bound work (PDF parsing, tokenizing, ONNX inference) directly on the event loop, blocking the entire server for the duration of each request. Fine on a fast local CPU; slow enough on Render's shared free-tier CPU to exceed the proxy's timeout
- **Fix**: wrapped each blocking call in `asyncio.to_thread()` so it runs on a separate thread instead of freezing the event loop
- **Bug (while editing)**: `tmp_path` referenced before the block that defines it, after a code edit moved a section out of order — `UnboundLocalError`
- **Bug (while editing)**: a leftover duplicate `try` block from a copy-paste, with the pipeline logic running twice
- **Bug**: `PydanticUserError: ... is not fully defined` — `ChatQuery`/`ChatResponse` were defined *below* the route (`/chat`) that referenced them as type hints; FastAPI/Pydantic need the class to exist in full before the route using it is registered. Fixed by moving the model classes above the routes
- **Real, separate memory bug**: after all the above was fixed, the Render instance was still crashing (`Instance failed`, confirmed via Render's Events tab) while embedding all 59 chunks in a single batch call — a genuinely different memory pressure point than the earlier `torch`-vs-`onnxruntime` fix. Fixing *how the model loads* did not fix *how much data gets pushed through it in one call*
- **Real fix**: rewrote `embed_chunks()` to process chunks in batches of 8 instead of all 59 at once — bounded memory usage without changing total work done
- Confirmed working end to end on Render after this fix

---

## Recurring lessons worth remembering (Week 2 additions)

- **A working local pipeline is not automatically a working deployed one.** Multiple bugs this week (`sentence_transformers` missing from `requirements.txt`, `python-multipart` missing, the self-import bug reappearing after deploy) only existed *because* something worked locally on faith without being verified against a fresh environment.
- **A `None` where a value was expected is one of the most traceable bug classes** — read the actual exception message; it almost always says exactly what's missing (`DATABASE_URL`, `GROQ_API_KEY`, `os`).
- **"Fixed the memory problem" needs to be scoped to the specific cause fixed, not treated as a permanent guarantee.** Two unrelated memory crashes happened on the same free-tier host this week, for two different reasons (model-loading overhead, then batch size during inference).
- **A silent 502 and a crash with a traceback are different failure classes**, and point you to different places to investigate — one means the app itself detected a problem, the other usually means something upstream gave up on a still-running app.
- **Aliased imports (`import x as y`) are invisible traps** for later code that assumes the standard name is available.
- **For anything version/availability-dependent on a third-party API** (model names, in this case), check the API's own live response (`client.models.list()`), not documentation or search results, which can lag behind real changes.
- **"No results" from a correctly-written, properly-scoped query is often a data-state mismatch, not a logic bug** — check what's actually stored before assuming the code is wrong.

---

## Where things stand heading into Week 3

- Full RAG pipeline working end-to-end, locally and deployed on Render: PDF upload → parse → chunk → embed (ONNX/MiniLM, batched) → store (Postgres/pgvector, tenant-isolated) → retrieve (`/chat`, similarity search) → generate (Groq, grounded via system prompt)
- Schema hardened: `NOT NULL` constraints and indexes in place on all tenant-scoped tables
- Deployment is real and stable — not just a local demo
- Not yet built: chat session logging into `chat_sessions`/`messages` (schema exists from Week 1, not wired into `/chat` yet), any frontend/dashboard integration, auth or rate limiting on `/chat`, and genuine multi-tenant testing with more than one real tenant's data
- Next up per the roadmap: multi-tenant UI wiring, chat session logging, and RLS policy writing (deferred from Day 10)

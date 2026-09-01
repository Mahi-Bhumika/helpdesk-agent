# LEARNING LOG
Week 1 — Learning Log (Bhumika)
 
Went from "install Node" on Day 1 to a live, deployed, end-to-end working app by Day 7 — Vercel frontend → Render backend → Supabase Postgres, real tenant rows landing in a real database, over the actual internet, not just localhost. Also survived a three-layer production bug in one sitting (typo → CORS → server crash) and came out the other side understanding why each layer failed, not just that it did.
 
What got built this week
Next.js app scaffolded (TypeScript, Tailwind, App Router), deployed live on Vercel
Repo structured as a monorepo (frontend/ + backend/), fully synced with partner's FastAPI work
ER diagram locked for all 8 core tables: users, tenants, documents, document_chunks, chat_sessions, messages, end_users, message_sources.
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

# Helpdesk Agent — Week 2 Learning Log - Bhumika

 # Week 2, Day 8, 9 (Tuesday) — Learning Log

## TL;DR
Went from zero Python environment on this machine to a working local embedding pipeline — `all-MiniLM-L6-v2` loaded, tested, and producing 384-dim vectors. Also reviewed a full extract → chunk → embed script (partner's work) that solved the token-exact chunking problem properly, using the model's own tokenizer instead of guessing at token counts.

## What got built
- Python venv set up in `backend/` from scratch (no Python previously installed on this machine)
- `sentence-transformers` installed and working; `all-MiniLM-L6-v2` downloaded and cached locally
- `embed.py`: a `get_embedding(text)` function, model loaded once at import time, tested on 3 sample sentences
- Reviewed partner's combined pipeline script: `extract_text()` (pdfplumber), `chunk_text()` (token-exact chunking via the model's own tokenizer, 250 tokens / 40 overlap), `embed_chunks()` (batch embedding)
- Locked chunking config: **250 tokens / 40 overlap** — deliberately below MiniLM's 256-token limit after catching that the original 400/50 default would've been silently truncated

## Concepts learned
- **Chunking, the "why":** exists to (1) fit the embedding model's context window and (2) keep chunks self-contained enough to be useful on retrieval — the "makes sense to a human alone = makes sense to the model" rule of thumb
- **Semantic search:** matches by meaning (vector distance) instead of literal keyword overlap
- **Lost-in-the-middle problem:** LLMs under-weight information buried in the middle of long context — argues for tuning `top_k` down to an optimal amount, not maxing it out
- **MiniLM's real limit is 256 tokens, not 512** — anything beyond that gets silently truncated, no error. This is why 400/50 (the generic default) was wrong for this specific model, and why 250/40 was the actual fix
- **Token-exact chunking:** using `tokenizer.encode()` / `tokenizer.decode()` directly (not character or word counts) guarantees chunks never exceed the model's real token limit
- **Batch embedding:** `model.encode(list_of_chunks)` in one call is faster than looping `model.encode(single_chunk)` per chunk — matters once you're embedding a real document's worth of chunks, not 2–3 test sentences
- **Model loading is expensive, do it once:** loading `SentenceTransformer(...)` at module/import level (not inside a function) avoids reloading the model on every single call
- **`__name__ == "__main__"`:** lets a file run test code when executed directly (`python embed.py`) without that code firing when the file is later imported elsewhere (`from embed import get_embedding`)
- **Type hints (`text: str`):** documentation for humans/tools, not runtime enforcement — Python won't stop you from passing the wrong type
- **Tokenizers aren't built by hand:** they come bundled with the pretrained model as a matched pair (`model.tokenizer`) — only training a model from scratch would require building one
- **Vector length as a sanity check:** every MiniLM embedding is 384 numbers regardless of input length; checking for consistent length + no `nan`/all-zero values confirms the pipeline is working, but says nothing about embedding *quality* — that only shows up later during real retrieval testing
- **Git stash:** temporarily shelves uncommitted changes so the working directory is clean (e.g. before a pull/branch switch), recoverable later with `git stash pop`

## The debugging saga
Another layered one, same pattern as Week 1's CORS saga — the visible error wasn't the real problem more than once:
1. **Duplicate venv** — VS Code auto-created its own `.venv` on top of the manually created one, without it being obvious two existed. Fixed by checking `pip list` in each and deleting the empty one.
2. **Pylance import errors (fastapi, pydantic, sqlalchemy, dotenv)** — looked like missing packages, was actually the interpreter pointing at the *right* venv, but with nothing installed in it yet.
3. **`pip install -r requirements.txt` → "No such file or directory"** — file existed, but the terminal was sitting in the repo root, not `backend/`, where the file actually lives. Path problem, not a missing-file problem.
4. **`TypeError: encode() missing 1 required positional argument`** — `model.encode()` was called with empty parentheses; the `text` argument silently got dropped when writing/copying the function.

**Lesson worth keeping:** most of today's errors *looked* like "this package/file doesn't exist," but were actually "you're pointed at the wrong place" — wrong venv, wrong directory, wrong argument. Checking *where* before assuming *what's missing* saved time once the pattern was recognized.

## What's still open
- Run the combined script end-to-end and actually read the real output (chunk count, first/last chunk text, embedding values)
- Confirm no `tokenizer.decode()` artifacts (odd spacing around punctuation) in the printed chunks
- Decide with partner which script becomes the canonical version feeding into Wednesday's pgvector schema work

## Week 2, Day 10 (Wednesday) — Learning Log

**TL;DR**

Verified the `document_chunks` table (partner's Day 10 work) end-to-end from the SQL editor — extension enabled, column typed correctly, dimension already locked to 384 — then successfully inserted a realistic ~250-word dummy chunk with a random 384-dim vector. Also picked back up an old Vim/git-pull snag from Day 1 and this time understood *why* the fix works, not just that it does.

**What got built**

- Verified `pgvector` extension is enabled via `pg_extension` system catalog query
- Verified `embedding` column's type and dimension via `information_schema.columns` and `pg_attribute.atttypmod` — confirmed already `vector(384)`, no `ALTER TABLE` needed
- Inserted one realistic dummy chunk (~250 words, password-reset-flow text) with `chunk_index = 0` and a randomly generated 384-length vector, using `RETURNING *` to confirm the row immediately
- Fixed a bad manual insert attempt (fake string IDs, missing column list) by switching to an explicit column list and letting Postgres auto-generate `chunk_id`

**Concepts learned**

- `character_maximum_length` in `information_schema.columns` only applies to character-based types (`varchar`/`char`) — it's expected to be blank for a `vector` column; it doesn't mean anything is wrong
- `atttypmod` (from `pg_attribute`) is the generic system-catalog field for type-specific metadata — for `vector`, it stores the dimension directly (no offset), unlike `varchar`'s `+4` header quirk. Corrected an earlier assumption about a `+4` offset applying universally — it doesn't
- **UUID format**: 32 hex digits grouped 8-4-4-4-12 (e.g. `a1b2c3d4-e5f6-4a3b-8c2d-9f0e1a2b3c4d`). A string like `'id1223'` isn't a valid UUID and Postgres rejects it outright when the column is typed `uuid`
- `gen_random_uuid()` isn't automatic just because a column is typed `uuid` — it only fires if the original `CREATE TABLE` (or Supabase's Table Editor UI, which adds it by default when using the visual tool) explicitly set it as the column's `DEFAULT`. Checked via `information_schema.columns.column_default` rather than assuming
- **Always specify an explicit column list in `INSERT`** — relying on positional order (no column list) means Postgres expects a value for *every* column in table order, and a mismatch throws `INSERT has more target columns than expressions`
- `RETURNING *` — appended to `INSERT`/`UPDATE`/`DELETE`, returns the affected row(s) immediately in the same query, avoiding a separate follow-up `SELECT`
- Revisited `git pull` → Vim merge-message prompt: `:wq` saves and completes the merge with the default message; `:q!` force-quits without saving (aborts the merge commit); plain `:q` often refuses to exit because Vim sees the pre-filled message as "unsaved"
- `git reset --hard origin/main` vs `git checkout origin/main -- <file>` vs `git stash`: three different scopes for "override local with remote" — full wipe, single-file overwrite, or temporary shelving — not interchangeable, matched to how much local work you actually want to keep

**The debugging saga**

- Attempted a manual `INSERT` with fake string values (`'id1223'`, etc.) and no column list — hit two stacked failures at once: wrong column count (6 values for 7 columns) and invalid UUID format on three columns simultaneously. Fixed by naming only the columns actually being set (`chunk_text`, `chunk_index`, `embedding`) and letting Postgres/defaults handle the rest
- Vim's merge-message prompt resurfaced (same as Day 1) — this time traced *why* `:wq` is the right call instead of just pattern-matching to "type this and it works"

**What confused you (the honest section)**

- Initially unsure whether `atttypmod` showing `384` meant the dimension was already correct or needed adjusting — turned out it was already right, no action needed, which felt anticlimactic after expecting to run an `ALTER TABLE`
- Assumed a missing `character_maximum_length` meant something was misconfigured — it was just the wrong metadata field to check for a `vector` type in the first place
- Wasn't sure whether Supabase "auto-generates" UUIDs as a platform-level guarantee — it's actually conditional on how the table was created (raw SQL `DEFAULT` clause vs. the Table Editor UI's convenience default), not a blanket rule

# Week 2, Day 11 — Findings (Full)

**Status: 🟡 OPEN — not resolved today, carries into next session**

## TL;DR
- Started as "write a test script for /kb/upload"
- Turned into a multi-layer production debugging chain
- Found and fixed **two real bugs** — insert loop + blocking event loop
- 502 **survived both fixes**
- Currently investigating a third hypothesis (possible OOM/memory kill)

---

## What got built
- `test_kb_upload.py` — creates a document row (`POST /documents`), uploads a file (`POST /kb/upload`), independently queries Supabase to verify chunk count + check for null embeddings
- Confirmed the real ingestion flow is **two separate calls**:
  - `POST /documents` → creates the row, returns `document_id`
  - `POST /kb/upload` → takes `document_id` + `tenant_id` + file, does the actual parse → chunk → embed → insert

### Bugs found (from reading actual `main.py` source)
- **Bug #1 — sequential insert loop**
  - One `await db.execute()` per chunk, in a `for` loop
  - 60+ chunks = 60+ sequential DB round-trips
- **Bug #2 — blocking the event loop**
  - `extract_text()`, `chunk_text()`, `embed_chunks()` are synchronous, CPU-heavy
  - Called directly (no `await`) inside an `async def` route
  - Freezes the **whole server**, not just that one request

### Fixes applied
- **Bug #1 fix:** build the full `rows` list first → one `db.execute()` call instead of looping
- **Bug #2 fix:** wrapped the three heavy calls in `asyncio.to_thread()` to run them in a background thread

### Result
- Still 502 — on both the Render `/docs` UI and the test script
- Rules out client-side causes a second time
- **Currently investigating:** possible OOM (out-of-memory) kill — `embed_chunks()` processes the whole chunk list in one batched call, holding it all in memory at once for bigger documents

---

## Concepts learned
- `async def` doesn't make code inside it non-blocking by default
  - A synchronous, CPU-heavy call inside an async route still freezes the event loop
  - Blocks *every* request the server would otherwise handle — including Render's own health checks
- `asyncio.to_thread(fn, *args)` runs an existing sync function in a background thread
  - The function itself stays untouched (`def`, not `async def`)
  - Only the *call site* changes to `await asyncio.to_thread(...)`
- `await` only works inside `async def` functions
  - Misplacing it → `"await allowed only within async function"`
- A real, confirmed fix doesn't guarantee the symptom disappears
  - More than one thing can be wrong at once
  - Ruling one cause out is still progress, even if the error persists
- Passing a list of param dicts to `db.execute()` collapses the *Python-level* loop
  - Doesn't strictly guarantee the driver sends it as one true network round-trip
  - "Fewer awaited calls" ≠ "fewer round-trips," necessarily
- OOM kills are a distinct failure mode from timeouts
  - A process killed for using too much RAM can also surface as a 502
  - Often nothing useful in normal logs — the process dies mid-request, no exception thrown
- Render's **Metrics** tab ≠ **Logs** tab
  - Logs = what the code said
  - Metrics = what the server was actually doing (CPU/RAM over time)
  - OOM kills often only show up in Metrics

---

## The debugging saga
1. Confirmed the 502 wasn't script-side — reproduced two ways (Render `/docs` UI + test script), same failure both ways → had to be server-side
2. Got the actual `main.py` source → found **Bug #1** (sequential insert loop) by reading code, not guessing further from behavior
3. Rewrote insert as a single batched call → retested → **502 persisted**
4. Re-read the code more carefully → found **Bug #2** (blocking event loop)
5. Hit `"await allowed only within async function"` while wiring in the fix
   - Traced to `await` being placed outside proper `async def` context
   - Fix belongs only inside `upload_document()`, not inside the sync helper functions
6. Applied corrected `asyncio.to_thread()` wrapping → retested → **still 502**
7. Stopped guessing blind a third time → switched to gathering actual evidence:
   - Checking Render's Metrics tab for a memory spike
   - Adding chunk-count logging to see how big `CPP_OOP_Notes.pdf` actually is vs. earlier smaller test docs

---

## What confused you (honest section)
- Assumed fixing one confirmed bug would resolve the symptom
  - Learned: a persistent symptom after a real fix doesn't mean the fix was wrong — could mean a second/third contributing cause
- Placed `await asyncio.to_thread(...)` outside a proper `async def` function
  - Triggered the "await allowed only within async function" error
  - Fix only belongs inside the route handler itself, not the helper functions it wraps
- Hadn't considered memory (OOM) as a failure category distinct from timeout
  - Both can look identical: 502 + quiet logs
  - Needed to rule out timeout-shaped causes first before memory became the next reasonable hypothesis

# Day 13 + 14 — Learning Log 

## What got built
- `/chat` endpoint in `main.py` — full RAG loop: query → embed → retrieve → generate → respond
- `ChatRequest` (tenant_id, query, top_k) and `ChatResponse` (answer, sources) Pydantic models
- Temporary stub for `search_similar_chunks()` to unblock work before partner's real version was ready
- Swapped stub → partner's real `search_similar_chunks()` + `generate_answer()` once done
- Reconciled two embedding functions: your `get_embedding()` (sentence-transformers) vs her `embed_chunks()` (ONNX)

## Errors hit
- Assumed Day 11/12 needed something "running" to start Day 13 — false; data in Supabase is permanent, no live server needed
- Leftover duplicate imports of `retrieval`/`generation` directly in `main.py` from an earlier pass — cleaned up, logic consolidated in one place
- Called `get_embedding()` but only `embed_chunks()` (partner's function) existed — name/signature mismatch, caught before running
- Silent bug: `embed_chunks(request.query)` passed a raw string instead of `list[str]` — wouldn't crash, would silently produce wrong embeddings — fixed via `embed_chunks([request.query])[0]`

## Concepts learned
- Stubbing: match name + signature + return shape → build/test independently → swap in real version later, zero other changes
- Routers (`APIRouter`) exist to stop two people editing the same `main.py` — not a FastAPI requirement, just a merge-conflict avoidance convention
- Retrieval ≠ generation: pgvector search is pure vector math (no LLM involved); the "NLP" already happened earlier at the embedding step
- Real-world NLP work (for ~everyone except foundation-model labs) = loading a pretrained model + building the pipeline around it, not training from scratch
- Batch vs. single-item functions: wrap single inputs in a list, unwrap the single result — same function, different call pattern
- Numerically compatible ≠ identical code: sentence-transformers `.encode()` and hand-rolled ONNX + mean-pooling + L2-normalize can produce the same math on different runtimes

## What confused you
- Thought router split was mandatory — it's optional, purely a collaboration convention
- Expected NLP to be far more manual/effort-heavy than it turned out to be — most of the hard part is already baked into the pretrained model
- Unsure if pgvector search itself "counts" as NLP — it doesn't; it's math over vectors the model already produced

## Open cross-check items (for her files)
- `embed.py`: same model weights as Day 9's chunks? same 384-dim output? truncation limit?
- `retrieval.py`: exact param names/order, async or not, exact returned dict keys, empty-result behavior
- `generation.py`: exact signature, expects raw chunks or pre-formatted string, which LLM API, async or not, empty-context behavior
- Shared DB connection setup across files, hardcoded values that need to move to env vars
- Has the full chain been tested end-to-end by her too, or only today in `/docs`?



# Helpdesk Agent — Week 3 Learning Log (Mahi)

---

## Summary

Went from an empty `frontend/` folder to a fully working Next.js dashboard — real Supabase auth (signup, email confirmation, login, logout), a protected route system, a working document upload pipeline hitting a live FastAPI backend, a tenant-scoped analytics view, and an editable bot settings page — all reading/writing a production Postgres database through Row-Level Security. Also uncovered and fixed a real backend bug (new signups weren't being linked to their tenant at all) that would have silently broken every tenant-scoped feature built on top of it.

---

## What got built this week

- Next.js dashboard scaffolded (TypeScript, Tailwind, App Router), `frontend/` folder alongside `backend/` in the shared repo
- Supabase client (`lib/supabase.ts`) and an app-wide `AuthProvider`/`useAuth` context (`lib/auth-context.tsx`) — session state and the logged-in user's `tenant_id` available on every page
- Signup page: collects tenant details (company name, type of business, subscription plan, bot name, greeting message, theme color), creates a Supabase auth account, links it to a new tenant, shows a "check your inbox" message instead of assuming an instant session
- Login page: real `signInWithPassword` call, error handling, redirect into the dashboard
- Protected `/dashboard/*` routes: redirect to `/login` if there's no session, with a loading state to avoid flashing dashboard content
- Logout button
- Document upload: drag-and-drop PDF upload (`react-dropzone`) → two-step backend call (`POST /documents` then `POST /kb/upload`) → live document list with filename and category, auto-refreshing after upload
- Analytics page: tenant-scoped counts of chat sessions and messages, pulled directly from Supabase
- Bot Settings page: edit and save bot name, greeting message, and theme color back to the tenant row
- Embed Script page: generates a tenant-specific `<script>` snippet with a copy button (widget host URL still a placeholder pending Bhumika's deploy)
- Five new Row-Level Security policies added (`users`, `documents`, `chat_sessions`, `messages`, `tenants` read + update) — RLS was enabled since Week 1 but had zero policies, so every tenant-scoped table was unreadable by default until this week
- Rebuilt `/chat` (backend) to actually use the schema it was designed for: creates a `chat_sessions` row on the first message (when `session_id` is null) and returns its id for the widget to reuse on follow-ups, logs both the user's question and the bot's answer into `messages`, and logs which chunks contributed to each answer into `message_sources` with a relevance score. Previously `/chat` answered questions statelessly — nothing was being saved, which is also why Analytics showed zero sessions/messages even after real testing
- Reviewed and negotiated the `/chat` request/response contract with Bhumika (widget side) before she wired up the send button — caught a mismatch between her proposed shape and what the backend actually returned, and confirmed the field name (`question`, not `query`) explicitly so neither side built against a guess

---

## Concepts learned (the real list)

- **Next.js App Router structure**: nested layouts, file-based routing, the difference between `app/layout.tsx` (wraps everything) and `app/dashboard/layout.tsx` (wraps only dashboard routes) — and what actually happens when code meant for one accidentally ends up in the other (two default exports in one file = build error)
- **Supabase Auth in practice**: `signUp`, `signInWithPassword`, `onAuthStateChange`, session persistence via `localStorage`, and the deliberately misleading response Supabase gives for a duplicate-email signup (`data.user.identities.length === 0` is the real signal, not `error`)
- **Row-Level Security, hands-on**: "enabled + no policy" means *nobody* can read a table, not even its owner — including you, querying your own data, with valid credentials. A 406 error from `.single()` on a query that should return exactly one row is the signature of this, and it's easy to mistake for a "row doesn't exist" bug when the row is actually sitting right there in the Table Editor
- **Environment variable structure matters exactly**: `NEXT_PUBLIC_SUPABASE_URL` must be the bare project URL — appending `/rest/v1` or any path breaks auth requests in a way that's easy to misdiagnose as a CORS or backend issue, since the resulting error ("Invalid path specified") doesn't obviously point at the env file
- **Frontend/backend split on tenant linking**: a signup flow can create a real Supabase auth account *and* a real tenant row and still leave them completely disconnected, if nothing explicitly writes the join. This isn't visible from the frontend — it only surfaces once something tries to answer "which tenant does this logged-in user belong to?"
- **NOT NULL constraints fail loudly, but not always where you're looking**: a backend INSERT missing required columns (`email`, `password_hash` in this case) throws a database error — but if the exception isn't surfacing anywhere visible in the frontend flow, it looks identical to "nothing happened," and the only way to actually confirm is checking Render's logs or the table directly
- **Local vs. deployed code are not the same code**: editing and testing a backend file locally does nothing for a frontend that's hardcoded to call the *deployed* Render URL. A fix has to be pushed and redeployed before the live app sees it — an easy trap when developing backend and frontend in two different places at once
- **Stale dev server cache**: Next.js's `.next` cache can occasionally serve old compiled code even after a file's contents visibly change on disk, surfacing as behavior that contradicts what's actually saved in the file. `rm -rf .next` + restart + hard browser refresh is the fix when console output stops matching the source
- **Render free-tier cold starts**: a backend that's been idle can take 30–50 seconds to respond to the first request, which looks identical to "broken" from the frontend if you don't know to expect it
- **Rate limits, plural**: Supabase enforces at least two separate limits during signup testing — a short per-attempt cooldown ("only request this after 46 seconds") and a broader email-sending cap ("email rate limit exceeded") — easy to conflate as the same issue when rapid-testing signup

---

## The debugging saga (worth remembering, not just logging)

Several separate bugs stacked on each other this week, and untangling which was which was most of the actual work:

1. **"Invalid path specified in request URL"** on signup → traced via the Network tab to a malformed request URL (`/rest/v1/auth/v1/signup` instead of `/auth/v1/signup`) → root cause was a path segment accidentally included in `NEXT_PUBLIC_SUPABASE_URL`
2. **Login appeared to do nothing** → console showed stale `"Login attempt :"` logs from an old version of the code, even though the file on disk was already correct → root cause was a stale `.next` build cache, not a code bug at all
3. **New tenant row created on every duplicate-email signup attempt** → Supabase returns a fake-success response for existing emails rather than an error, so the code sailed past the auth check and created an orphaned tenant every time → fixed by checking `data.user.identities.length === 0` before proceeding
4. **Backend "fix" for linking users to tenants silently did nothing** → the INSERT was missing two `NOT NULL` columns (`email`, `password_hash`) that only existed once the real `schema.sql` was actually checked, rather than assumed
5. **`tenantId` stuck on "Loading your account..." forever, four repeated 406 errors in console** → row genuinely existed in the `users` table, but RLS was enabled with zero read policy, so the anon-key query returned nothing without throwing a visible error — fixed with an explicit `auth.uid() = user_id` policy

The throughline: **almost none of these failed loudly with an obviously-correct error message.** Each one required actually looking — Network tab, Render logs, the Table Editor directly — rather than assuming from a vague symptom ("nothing happened," "it's slow," "the page won't load") what the cause must be.

---

## What confused me (honest list)

- Assumed early on that a `console.log` still appearing after a code change meant the edit hadn't saved — didn't initially consider that the dev server's cache could be serving old compiled output independent of the source file
- Didn't realize Supabase deliberately obscures whether an email is already registered (returns "success" either way) — cost a few duplicate tenant rows before catching it
- Conflated two different Supabase rate limits (per-attempt cooldown vs. email-sending cap) as the same thing at first
- Assumed the confirmation-email redirect page failing to load meant the confirmation itself hadn't registered — they're actually unrelated; the account can be fully confirmed server-side even if the post-click redirect page errors out client-side
- Underestimated how much of "it's not working" during this week was actually RLS silently returning nothing, rather than a bug in the query or component logic itself — this pattern repeated three separate times (`users`, `documents`, and pre-emptively for `chat_sessions`/`messages`/`tenants`) before it became the first thing to check

---

## Where things stand heading into Week 4

- Frontend and backend are fully connected for the core owner flow: signup → email confirmation → login → upload documents → view them → see analytics → edit bot settings → generate an embed snippet
- Five RLS policies now exist; per the Week 1 plan, full RLS policy work was scheduled for Week 4 — a meaningful chunk of it already landed early, out of necessity
- The embed snippet is functionally complete but points at a placeholder widget URL, pending Bhumika's deployed `widget.js`
- The joint milestone (owner's embed snippet working on a real dummy page, widget talking to the same backend as the dashboard) is the one piece still blocked on both sides being ready at the same time
- Next up per the roadmap: Week 4 — remaining RLS policy coverage, invite flow, and closing the loop on the full end-to-end demo with Bhumika's widget

# Week 3 — Learning Log (Bhumika)

Went from an empty `widget.js` skeleton on Day 15 to a genuinely
production-tested embeddable chat widget by Day 21 — Shadow DOM
isolated, wired to the live Render backend, CORS-safe two different
ways, rate-limited against direct abuse, and hosted publicly on
Vercel + GitHub Pages, not just proven on localhost. Also chased a
CORS bug into what turned out to be a completely unrelated local
`.env` crash, which is worth its own section below — same shape of
lesson as Week 1's CORS saga, wearing a different disguise.

## What got built this week

- **Day 15** — `widget.js` skeleton: IIFE-wrapped so nothing leaks
  into a tenant's global scope, reads its own config
  (`tenantId`/`apiUrl`/`color`/`position`) off its own `<script>` tag
  via `data-*` attributes, floating bubble + toggleable panel shell
- **Day 16** — real message list UI: bot/user message bubbles,
  input + send footer, a first-open greeting message
- **Day 17** — wired the send button to a real `POST /chat` call —
  `fetch`/Promise chain, error handling, `session_id` threading
  (flagged a real contract gap: backend's `ChatResponse` doesn't
  return `session_id` yet, so multi-turn memory doesn't actually
  persist server-side until that's added)
- **Day 18** — moved the whole widget into Shadow DOM
  (`attachShadow`) for genuine CSS isolation — verified for real,
  not just assumed, against a deliberately hostile test page
  (`demo-aggressive-css.html`, `!important` rules on every
  `button`/`div`/`input`) — bubble and panel stayed completely
  unaffected
- **Day 19** — typing/loading indicator (bouncing dots via CSS
  `@keyframes`), input + send button disabled while a request is in
  flight so you can't double-fire a message
- **Day 20** — CORS, two ways: **Option A** (global wildcard
  `CORSMiddleware`, handed off to my teammate to unblock the
  Sat/Sun milestone fast) and **Option B** (custom path-aware
  middleware I actually built — `/chat` gets wildcard + no
  credentials, dashboard routes get a strict origin allowlist +
  credentials — verified with a real `TestClient` across four
  scenarios, not just written and assumed correct)
- **Day 21** — packaged `widget.js` as a genuinely standalone file,
  proved three ways: a local 3-terminal cross-origin simulation
  (`embed-test-site/`, three real ports acting as three real
  origins), then actual public hosting (Vercel's `public/` folder +
  GitHub Pages), confirmed end-to-end against the *live* Render
  backend — real answer, real 200, real CORS headers
- **Unplanned but shipped anyway** — rate limiting on `/chat`
  (sliding window, per-`tenant_id`), after realizing `tenant_id`
  being necessarily public (it's in the embed script by design)
  means anyone could scrape it and hit `/chat` directly with a
  script — no browser, no widget, no CORS involved at all. Tested
  against a real FastAPI route with an actual 1.1-second real-time
  sleep to prove the window really slides, not just claimed to

## Concepts learned (the real list)

- **IIFE + closures, properly understood this time** — the actual
  mechanism behind how `sessionId`/`hasGreeted`/`isSending` "remember"
  state across multiple button clicks with zero global variables and
  zero framework. `mountWidget()` runs once and returns, but the
  functions it defines keep living as event listeners, still holding
  onto its local variables forever
- **`textContent` vs `innerHTML` — the real reason, not just a style
  choice.** Never let visitor-typed or bot-generated text pass
  through `innerHTML` — that's the actual XSS boundary, not a
  cosmetic preference
- **Promise chains** — `.then()`/`.catch()`/`.finally()`, and that a
  `throw` inside a `.then()` routes straight to the nearest `.catch()`
  instead of crashing the page
- **Shadow DOM, the full mechanism** — `attachShadow()` creates a
  genuinely separate DOM tree that host-page CSS *rules* can't match
  into. But rule-matching isolation and *property inheritance* are
  two different things — `:host{all:initial}` is needed on top,
  because inherited properties (font, color, line-height) still flow
  in from the host page's `<body>` unless explicitly reset
- **CSS specificity/cascade, for real this time** — the `[hidden]`
  bug from Day 15 revisited with actual vocabulary: two rules of
  equal specificity resolve by *source order*, not by which one
  "feels" more specific
- **Flexbox in practice** — `align-self` vs `align-items`,
  `flex-shrink: 0`, `gap`, and why `align-self: flex-end` still means
  "push right" even inside a `flex-direction: column` container
  (cross-axis, not main-axis)
- **CORS is a browser-JS restriction, not a security boundary** — a
  plain script or `curl` loop ignores it completely. RLS is the
  actual data boundary; CORS and rate limiting are cost/abuse
  boundaries, a genuinely different job
- **Public identifiers vs real secrets** — `tenant_id` and the API
  base URL are *supposed* to be visible, same category as a Stripe
  publishable key. Real secrets are the ones that touch
  billing/DB/LLM API keys directly, and env vars don't make a
  client-shipped value secret — they just avoid hardcoding it across
  files
- **Why env vars can't hide anything inside an embed script** — no
  build step exists on a *tenant's own* website. There's no live
  connection back to my Vercel project for a secret to travel through
  at request time, even if I wanted one to — the value has to be
  sitting in the pasted HTML, permanently, by construction
- **Sliding window vs fixed window rate limiting** — fixed windows
  have a real edge case (a burst of 2x the limit across a window
  boundary slips through, each half technically within its own
  window). Sliding avoids it by dropping only timestamps older than
  the window on every check, instead of resetting a counter on a
  clock tick

## Real bugs found and fixed

1. **`[hidden]` silently overridden by `.botai-panel{display:flex}`**
   — a CSS specificity tie, broken by declaration order, invisible
   until actually traced rather than guessed at
2. **Local `DATABASE_URL` crash mid-CORS-debugging** — same bug
   *class* as Week 1's Day 11 (`os.getenv()` silently returning
   `None`), but this time it was a complete red herring: an unrelated
   local `.env` problem on my own machine, surfacing at the exact
   moment I was testing a teammate's CORS fix, initially looked like
   it might be connected and wasn't
3. **422 on the live `/chat` call** — request body shape mismatch,
   the `session_id` contract gap flagged all the way back on Day 15
   finally surfacing for real the moment a real backend was actually
   hit instead of a stub

## Decisions made deliberately, not by default

- Shipped **Option A** (global wildcard CORS) to hit the Sat/Sun
  milestone on time, deliberately deferring the more-correct
  **Option B** to buffer week — then actually built Option B once
  there was room, instead of letting "worth doing later" quietly
  never happen
- Chose **in-memory** rate limiting over Redis/Postgres-backed —
  correct tradeoff for a single free-tier Render instance, explicitly
  documented as needing to change the moment this app ever scales
  past one instance
- Chose **Vercel's `public/` folder** over jsDelivr for hosting
  `widget.js` — zero new signups, uses infrastructure already
  deployed, accepted "manually `cp` the file before pushing" as a
  genuinely fine rough edge at this project's size rather than
  building automation the problem doesn't need yet

## The debugging saga worth remembering

Testing my teammate's Option A CORS fix, the local backend crashed at
*startup* — not a `/chat` runtime error, not CORS at all,
`uvicorn`/`importlib` failing before the app ever came up. The
traceback's first two screenshots only showed generic Python import
machinery (`_gcd_import`, `import_module`) — every import-time crash
looks identical that far up the stack. The actually useful line only
showed up at the very bottom of the *third* screenshot:
`sqlalchemy.exc.ArgumentError: Expected string or URL object, got
None` — `DATABASE_URL` was `None` locally, unrelated to anything
either of us had touched that day.

**The lesson, restated because it keeps being true:** the first error
you see is where the trace *ends up*, not necessarily where the
actual bug *is*. Once local was untangled from that and confirmed
irrelevant, the real CORS retest against the live Render backend
worked cleanly — preflight succeeded, and the next real bug (422) was
a completely different, much smaller issue: a request-shape mismatch,
solved by reading the actual `detail` array FastAPI hands back instead
of guessing at which field was wrong.

## What confused me (the honest section)

- Initially reached for "just deploy `widget.js` and test against
  that" as a fix for a CORS/422 issue that was 100% backend-side —
  mixed up which layer actually owned the bug, and deploying the
  wrong layer wouldn't have told me anything
- Thought putting `tenant_id`/`apiUrl` in Vercel env vars would hide
  them from a public embed script — hadn't separated "avoids
  hardcoding across files" from "makes something actually secret,"
  and hadn't clocked that env vars only get read at *build* time by
  *my own* project, not by an unrelated third-party site with zero
  connection back to it
- Got a CORS-shaped error that turned out to be an entirely
  unconnected local `.env` problem — the exact same "the visible
  error isn't always the real one" trap from Week 1, showing up again
  in a new shape
# Debug Log — Aug 30, 2026

Session: Vercel deploy + local dev issues after Mahi's README/dashboard-auth push. Four separate, unrelated bugs, fixed one at a time.

---

## 1. Vercel build — TS2306: File is not a module

**Where:** Vercel production build
**Error:**
```
.next/types/validator.ts(69,39): error TS2306: File '/vercel/path0/frontend/app/dashboard/sessions/page.tsx' is not a module.
```

**Cause:** `app/dashboard/sessions/page.tsx` existed but had no `import`/`export` statements (empty or stub file). Next.js's auto-generated route type-checker requires every `page.tsx` to have a valid `export default`, so TypeScript couldn't treat the file as a module at all.

**Likely origin:** File was created locally, never committed/pushed until it hitched a ride on the README commit (`git add -A` / `git commit -a` scoops up untracked files).

**Fix:** Deleted the stub file. (Longer-term: any placeholder route file needs at least a minimal `export default function Page() { return <div/> }` before committing.)

**Follow-up worth doing:** `git log --follow -- frontend/app/dashboard/sessions/page.tsx` to confirm exactly when it was first pushed, and check Vercel's Deployments tab for whether yesterday's build was silently red.

---

## 2. Vercel build — `supabaseUrl is required`

**Where:** Vercel production build, during static prerender of `_not-found` page
**Error:**
```
Error: supabaseUrl is required.
  at module evaluation (lib/supabase.ts:4:14)
  at module evaluation (lib/auth-context.tsx:4:1)
```

**Cause:** `lib/supabase.ts` calls `createClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, ...)` at module top-level. `auth-context.tsx` wraps the app (likely via root layout), so this module loads during Next.js's build-time prerender of every page — including the auto-generated 404 page. `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY` were never set in **Vercel's** Environment Variables (existing only in local `.env.local`, which Vercel never reads).

**Fix:** Add both vars in Vercel → Project Settings → Environment Variables, scoped to Production (and Preview if needed), then redeploy (env var changes don't auto-trigger a rebuild of existing deployments).

---

## 3. npm warning — `allow-scripts` (esbuild, unrs-resolver)

**Where:** `npm install` output, both local and Vercel build logs
**Warning:**
```
npm warn allow-scripts 2 packages have install scripts not yet covered by allowScripts:
npm warn allow-scripts   esbuild@0.28.2 (postinstall: node install.js)
npm warn allow-scripts   unrs-resolver@1.12.2 (postinstall: node postinstall.js)
```

**Verdict: not a bug.** This is a newer npm supply-chain-security feature — it skips running postinstall scripts for packages not yet on an approved list, but the install itself completes normally. Packages were still installed into `node_modules`; only their postinstall scripts were skipped. `npm approve-scripts --allow-scripts-pending` returning "none" just confirms there's nothing left pending — not a failure.

**Action taken:** None needed. Confirmed via `ls node_modules/esbuild` / `ls node_modules/unrs-resolver` that both were present.

---

## 4. Local dev — Module not found: `@supabase/supabase-js`

**Where:** `localhost:3000`, Mahi's machine
**Error:**
```
Module not found: Can't resolve '@supabase/supabase-js'
./lib/supabase.ts (2:1)
```

**Cause:** `lib/supabase.ts` imports `@supabase/supabase-js`, but the package was never installed on her machine — `npm install @supabase/supabase-js` was never run (code was written/copied without the install step).

**Fix:** `npm install @supabase/supabase-js` in `frontend/`, restart dev server. (Note: `npm install <pkg>` auto-adds it to `package.json` — no manual edit needed.)

---

## 5. Local install — `npm error ECONNRESET`

**Where:** Same machine, while running the fix for #4
**Error:**
```
npm error code ECONNRESET
npm error network Invalid response body while trying to fetch https://registry.npmjs.org/@supabase%2fsupabase-js
```

**Cause:** Network-level connection drop to npm's registry — not a code or config issue. Common with unstable wifi, VPNs, campus/public networks, or antivirus/firewall interference.

**Fix:** Retried the same install command — resolved on retry (registry blips are common; not worth deep investigation unless it fails repeatedly).

---

## Recurring pattern across all 5

Every single one of these was a **separate, unrelated** cause surfaced one at a time by fixing the previous error and re-running — not one root problem. Matches the pattern already logged in Week 1/2: the first visible error is rarely the last one, and each fix just uncovers the next layer. Worth remembering for future deploys: don't assume "fixed" until a build actually goes green end-to-end.


## Heading into Week 4

Widget is functionally complete and genuinely production-tested, not
just locally simulated: Shadow DOM isolated, real backend wired,
CORS handled two ways, rate-limited against direct-script abuse,
hosted publicly on both Vercel and GitHub Pages. Open items carried
forward, not forgotten: confirm the backend is actually returning
`session_id` for real multi-turn threading; decide with my teammate
whether Option A or Option B CORS is what actually ships; confirm
`rate_limit.py` got merged in. Next up per the plan: RLS policies +
the attack script (Week 4's real focus), starting with my own Monday
task — standing up a second test tenant with a different sample PDF,
so there's something real for the attack script to try (and fail) to
reach.

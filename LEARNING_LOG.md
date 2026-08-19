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

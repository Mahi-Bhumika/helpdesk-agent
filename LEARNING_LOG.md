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

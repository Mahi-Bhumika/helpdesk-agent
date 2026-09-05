
## Run — 2026-09-03 06:14 UTC

| Path | Table | Op | Status | Detail |
|---|---|---|---|---|
| supabase_direct | tenants | read | **PASS** | 0 rows returned |
| supabase_direct | users | read | **PASS** | 0 rows returned |
| supabase_direct | documents | read | **PASS** | 0 rows returned |
| supabase_direct | document_chunks | read | **PASS** | 0 rows returned |
| supabase_direct | chat_sessions | read | **PASS** | 0 rows returned |
| supabase_direct | messages | read | **PASS** | 0 rows returned |
| supabase_direct | end_users | read | **PASS** | 0 rows returned |
| supabase_direct | documents | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | document_chunks | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | chat_sessions | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | messages | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | users | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | end_users | write | **PASS** | blocked by RLS policy (403) |
| fastapi | chat_sessions+messages | read+write | **CHECK** | request error: HTTPSConnectionPool(host='helpdesk-agent-9eu9.onrender.com', port=443): Read timed out. (read timeout=30) |
| — | message_sources | — | **SKIP** | no tenant_id column — needs a manual test via a known message_id once one has leaked; RLS here must be join/EXISTS-based, not a plain compare |

## Run — 2026-09-03 07:27 UTC

| Path | Table | Op | Status | Detail |
|---|---|---|---|---|
| supabase_direct | tenants | read | **PASS** | 0 rows returned |
| supabase_direct | users | read | **PASS** | 0 rows returned |
| supabase_direct | documents | read | **PASS** | 0 rows returned |
| supabase_direct | document_chunks | read | **PASS** | 0 rows returned |
| supabase_direct | chat_sessions | read | **PASS** | 0 rows returned |
| supabase_direct | messages | read | **PASS** | 0 rows returned |
| supabase_direct | end_users | read | **PASS** | 0 rows returned |
| supabase_direct | documents | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | document_chunks | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | chat_sessions | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | messages | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | users | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | end_users | write | **PASS** | blocked by RLS policy (403) |
| fastapi | chat_sessions+messages | read+write | **CHECK** | request error: HTTPSConnectionPool(host='helpdesk-agent-9eu9.onrender.com', port=443): Read timed out. (read timeout=30) |
| — | message_sources | — | **SKIP** | no tenant_id column — needs a manual test via a known message_id once one has leaked; RLS here must be join/EXISTS-based, not a plain compare |

## Run — 2026-09-04 03:31 UTC

| Path | Table | Op | Status | Detail |
|---|---|---|---|---|
| supabase_direct | tenants | read | **PASS** | 0 rows returned |
| supabase_direct | users | read | **PASS** | 0 rows returned |
| supabase_direct | documents | read | **PASS** | 0 rows returned |
| supabase_direct | document_chunks | read | **PASS** | 0 rows returned |
| supabase_direct | chat_sessions | read | **PASS** | 0 rows returned |
| supabase_direct | messages | read | **PASS** | 0 rows returned |
| supabase_direct | end_users | read | **PASS** | 0 rows returned |
| supabase_direct | documents | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | document_chunks | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | chat_sessions | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | messages | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | users | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | end_users | write | **PASS** | blocked by RLS policy (403) |
| fastapi | chat_sessions+messages | read+write | **CHECK** | request error: HTTPSConnectionPool(host='helpdesk-agent-9eu9.onrender.com', port=443): Read timed out. (read timeout=30) |
| — | message_sources | — | **SKIP** | no tenant_id column — needs a manual test via a known message_id once one has leaked; RLS here must be join/EXISTS-based, not a plain compare |

## Run — 2026-09-04 03:41 UTC

| Path | Table | Op | Status | Detail |
|---|---|---|---|---|
| supabase_direct | tenants | read | **PASS** | 0 rows cross-tenant; 1 row(s) of own data confirmed readable — real isolation, not a blanket lockout |
| supabase_direct | users | read | **PASS** | 0 rows cross-tenant; 1 row(s) of own data confirmed readable — real isolation, not a blanket lockout |
| supabase_direct | documents | read | **PASS** | 0 rows cross-tenant; 1 row(s) of own data confirmed readable — real isolation, not a blanket lockout |
| supabase_direct | document_chunks | read | **PASS** | 0 rows cross-tenant; 6 row(s) of own data confirmed readable — real isolation, not a blanket lockout |
| supabase_direct | chat_sessions | read | **CHECK** | 0 rows cross-tenant AND 0 rows for own tenant — can't confirm this is real isolation vs. a table with no SELECT policy at all (locked for everyone, owner included). Either insert a known row for this tenant and rerun, or confirm via the Supabase Table Editor that a policy actually exists. |
| supabase_direct | messages | read | **CHECK** | 0 rows cross-tenant AND 0 rows for own tenant — can't confirm this is real isolation vs. a table with no SELECT policy at all (locked for everyone, owner included). Either insert a known row for this tenant and rerun, or confirm via the Supabase Table Editor that a policy actually exists. |
| supabase_direct | end_users | read | **CHECK** | 0 rows cross-tenant AND 0 rows for own tenant — can't confirm this is real isolation vs. a table with no SELECT policy at all (locked for everyone, owner included). Either insert a known row for this tenant and rerun, or confirm via the Supabase Table Editor that a policy actually exists. |
| supabase_direct | documents | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | document_chunks | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | chat_sessions | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | messages | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | users | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | end_users | write | **PASS** | blocked by RLS policy (403) |
| fastapi | chat_sessions+messages | read+write | **CHECK** | unexpected status 422: {"detail":[{"type":"missing","loc":["body","question"],"msg":"Field required","input":{"tenant_id":"2ed03743-767d-4e52-aa99-9a3ebf8d4cf6","query":"ATTACK-TEST probe question — ignore if seen in real c |
| — | message_sources | — | **SKIP** | no tenant_id column — needs a manual test via a known message_id once one has leaked; RLS here must be join/EXISTS-based, not a plain compare |

## Run — 2026-09-04 03:54 UTC

| Path | Table | Op | Status | Detail |
|---|---|---|---|---|
| supabase_direct | tenants | read | **PASS** | 0 rows cross-tenant; 1 row(s) of own data confirmed readable — real isolation, not a blanket lockout |
| supabase_direct | users | read | **PASS** | 0 rows cross-tenant; 1 row(s) of own data confirmed readable — real isolation, not a blanket lockout |
| supabase_direct | documents | read | **PASS** | 0 rows cross-tenant; 1 row(s) of own data confirmed readable — real isolation, not a blanket lockout |
| supabase_direct | document_chunks | read | **PASS** | 0 rows cross-tenant; 6 row(s) of own data confirmed readable — real isolation, not a blanket lockout |
| supabase_direct | chat_sessions | read | **CHECK** | 0 rows cross-tenant AND 0 rows for own tenant — can't confirm this is real isolation vs. a table with no SELECT policy at all (locked for everyone, owner included). Either insert a known row for this tenant and rerun, or confirm via the Supabase Table Editor that a policy actually exists. |
| supabase_direct | messages | read | **CHECK** | 0 rows cross-tenant AND 0 rows for own tenant — can't confirm this is real isolation vs. a table with no SELECT policy at all (locked for everyone, owner included). Either insert a known row for this tenant and rerun, or confirm via the Supabase Table Editor that a policy actually exists. |
| supabase_direct | end_users | read | **CHECK** | 0 rows cross-tenant AND 0 rows for own tenant — can't confirm this is real isolation vs. a table with no SELECT policy at all (locked for everyone, owner included). Either insert a known row for this tenant and rerun, or confirm via the Supabase Table Editor that a policy actually exists. |
| supabase_direct | documents | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | document_chunks | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | chat_sessions | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | messages | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | users | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | end_users | write | **PASS** | blocked by RLS policy (403) |
| fastapi | chat_sessions+messages | read+write | **PASS** | rejected (403) — auth check is working |
| — | message_sources | — | **SKIP** | no tenant_id column — needs a manual test via a known message_id once one has leaked; RLS here must be join/EXISTS-based, not a plain compare |

## Run — 2026-09-04 06:32 UTC

| Path | Table | Op | Status | Detail |
|---|---|---|---|---|
| supabase_direct | tenants | read | **PASS** | 0 rows cross-tenant; 1 row(s) of own data confirmed readable — real isolation, not a blanket lockout |
| supabase_direct | users | read | **PASS** | 0 rows cross-tenant; 1 row(s) of own data confirmed readable — real isolation, not a blanket lockout |
| supabase_direct | documents | read | **PASS** | 0 rows cross-tenant; 1 row(s) of own data confirmed readable — real isolation, not a blanket lockout |
| supabase_direct | document_chunks | read | **PASS** | 0 rows cross-tenant; 6 row(s) of own data confirmed readable — real isolation, not a blanket lockout |
| supabase_direct | chat_sessions | read | **PASS** | 0 rows cross-tenant; 1 row(s) of own data confirmed readable — real isolation, not a blanket lockout |
| supabase_direct | messages | read | **PASS** | 0 rows cross-tenant; 1 row(s) of own data confirmed readable — real isolation, not a blanket lockout |
| supabase_direct | end_users | read | **CHECK** | 0 rows cross-tenant AND 0 rows for own tenant — can't confirm this is real isolation vs. a table with no SELECT policy at all (locked for everyone, owner included). Either insert a known row for this tenant and rerun, or confirm via the Supabase Table Editor that a policy actually exists. |
| supabase_direct | documents | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | document_chunks | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | chat_sessions | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | messages | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | users | write | **PASS** | blocked by RLS policy (403) |
| supabase_direct | end_users | write | **PASS** | blocked by RLS policy (403) |
| fastapi | chat_sessions+messages | read+write | **PASS** | rejected (403) — auth check is working |
| — | message_sources | — | **SKIP** | no tenant_id column — needs a manual test via a known message_id once one has leaked; RLS here must be join/EXISTS-based, not a plain compare |

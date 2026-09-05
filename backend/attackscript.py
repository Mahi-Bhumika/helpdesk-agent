"""
cross_tenant_attack_test.py

Week 4, Day 2 (Tue) task: a repeatable attack script that tests multi-tenant
data isolation across BOTH paths a tenant's data can be reached through:

  1. "supabase_direct" — anon-key + JWT calls straight to Supabase's REST
     API (PostgREST). This is the path the dashboard's Analytics/Settings/
     Documents-list pages use, and the ONLY path Postgres RLS actually
     protects.

  2. "fastapi" — calls to our own FastAPI backend. As of Week 4
     Day 1, /chat trusts tenant_id from the request body with zero auth,
     which is the vulnerability Mahi found manually with curl.

For every tenant-scoped table, we log in as Tenant A and try to READ and
WRITE rows that belong to Tenant B, and log a PASS / FAIL / CHECK per
table per path.

  PASS  = isolation held (no cross-tenant read, write correctly blocked
          by an RLS policy)
  FAIL  = isolation broken (cross-tenant data returned, or a cross-tenant
          write succeeded)
  CHECK = write was blocked, but not provably *by RLS* (could be an
          unrelated constraint) — read the "detail" field yourself
  SKIP  = table intentionally not auto-tested (see NOTES below)

Re-run this exact script every day this week:
  Tue (today) — baseline, before any RLS policies exist. Expect FAIL
                everywhere. That's not a bug in the script — that's the
                confirmed baseline Mahi already proved manually.
  Wed         — after users/tenants policies land, re-run and expect
                those two tables (only) to flip to PASS on the
                supabase_direct path.
  Wed (later) — after documents/document_chunks/message_sources land,
                same thing for those.
  Thu         — after Authorization: Bearer wiring lands on FastAPI,
                re-run with --attacker-token to test the fastapi path
                for real (see usage below).
  Sun         — full regression, both paths, everything should be PASS.

NOTES:
  - `message_sources` has NO tenant_id column in the schema (only
    message_id, chunk_id, relevance_score). It can't be tested with a
    simple tenant_id filter, so it's SKIPped by the automated read/write
    tests below and needs a manual test once you have a real message_id
    to probe with. Its RLS policy will have to be a join/EXISTS check
    against messages or document_chunks, not a plain tenant_id compare —
    flag this to Mahi if the "helper" mentioned for Wednesday doesn't
    already account for it.
  - Inserting into `tenants` itself isn't really a "cross-tenant" attack
    in the same sense as the others, so it's excluded from the write test.

Usage:
    pip install requests python-dotenv --break-system-packages
    cp .env.attack.example .env.attack
    # fill in .env.attack with real values
    python cross_tenant_attack_test.py

    # once FastAPI auth is wired (Thursday), also pass a valid token for
    # Tenant A so the fastapi path test is meaningful post-fix:
    python cross_tenant_attack_test.py --attacker-token "<tenant A JWT>"

    # to skip the write (INSERT) attacks and only run reads:
    python cross_tenant_attack_test.py --read-only
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from uuid import uuid4

import requests
from dotenv import load_dotenv

load_dotenv(".env.attack")

#config

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
FASTAPI_BASE_URL = os.getenv("FASTAPI_BASE_URL", "").rstrip("/")

TENANT_A_EMAIL = os.getenv("TENANT_A_EMAIL", "")
TENANT_A_PASSWORD = os.getenv("TENANT_A_PASSWORD", "")
TENANT_A_ID = os.getenv("TENANT_A_ID", "")

TENANT_B_EMAIL = os.getenv("TENANT_B_EMAIL", "")
TENANT_B_PASSWORD = os.getenv("TENANT_B_PASSWORD", "")
TENANT_B_ID = os.getenv("TENANT_B_ID", "")

REQUIRED_VARS = [
    "SUPABASE_URL", "SUPABASE_ANON_KEY", "FASTAPI_BASE_URL",
    "TENANT_A_EMAIL", "TENANT_A_PASSWORD", "TENANT_A_ID",
    "TENANT_B_EMAIL", "TENANT_B_PASSWORD", "TENANT_B_ID",
]


def check_config():
    missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
    if missing:
        print("Missing required .env.attack values:", ", ".join(missing))
        sys.exit(1)


#Table config
# Tables to attempt a cross-tenant READ against (filter on tenant_id)

READ_TEST_TABLES = [
    "tenants", "users", "documents", "document_chunks",
    "chat_sessions", "messages", "end_users",
]
 
# Tables to attempt a cross-tenant WRITE against, and the minimal payload
# needed to satisfy each table's NOT NULL columns. Payload is a function of
# the victim tenant_id so every attack run is easy to spot/clean up later
# (everything is tagged "ATTACK-TEST").
def _write_payloads(victim_tenant_id: str):
    tag = f"ATTACK-TEST-{uuid4().hex[:8]}"
    return {
        "documents": {
            "tenant_id": victim_tenant_id,
            "file_url": f"https://attack-test.invalid/{tag}.pdf",
            "format": "pdf",
            "status": tag,
            "theme": tag,
        },
        "document_chunks": {
            "tenant_id": victim_tenant_id,
            "chunk_text": f"{tag} — chunk injected by cross_tenant_attack_test.py",
            "chunk_index": 999999,
        },
        "chat_sessions": {
            "tenant_id": victim_tenant_id,
            "textual_feedback": tag,
        },
        "messages": {
            "tenant_id": victim_tenant_id,
            "sender": "attacker",
            "content": f"{tag} — message injected by cross_tenant_attack_test.py",
        },
        "users": {
            "tenant_id": victim_tenant_id,
            "name": tag,
            "email": f"{tag}@example.com",
            "password_hash": "not_a_real_hash",
            "role": "member",
            "status": tag,
        },
        "end_users": {
            "tenant_id": victim_tenant_id,
            "name": tag,
            "email": f"{tag}@example.com",
        },
    }
 
 
# Tables intentionally excluded from automated read and/or write tests,
# with the reason, so the report doesn't silently look "clean" for them.
SKIPPED = {
    "message_sources": "no tenant_id column — needs a manual test via a "
                        "known message_id once one has leaked; RLS here "
                        "must be join/EXISTS-based, not a plain compare",
}
 
 
# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
 
def get_jwt(email: str, password: str) -> str:
    resp = requests.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Login failed for {email}: {resp.status_code} {resp.text}")
    return resp.json()["access_token"]
 
 
# ---------------------------------------------------------------------------
# Supabase-direct attacks
# ---------------------------------------------------------------------------
 
def supabase_headers(jwt: str) -> dict:
    return {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {jwt}",
        "Content-Type": "application/json",
    }
 
 
def _supabase_read_count(table: str, jwt: str, tenant_id: str):
    """Returns (row_count, error_detail_or_None)."""
    url = f"{SUPABASE_URL}/rest/v1/{table}?tenant_id=eq.{tenant_id}&select=*"
    try:
        resp = requests.get(url, headers=supabase_headers(jwt), timeout=15)
    except requests.RequestException as e:
        return None, f"request error: {e}"
    if resp.status_code != 200:
        return None, f"unexpected status {resp.status_code}: {resp.text[:200]}"
    rows = resp.json()
    return len(rows) if isinstance(rows, list) else None, None
 
 
def attack_supabase_read(table: str, attacker_jwt: str, attacker_tenant_id: str,
                          victim_tenant_id: str) -> dict:
    """
    Two queries, not one:
      1. attacker -> victim's tenant_id   (the actual attack)
      2. attacker -> their OWN tenant_id  (control — proves the table isn't
         just locked for everyone, which would make a 0-row "win" meaningless)
 
    Without the control, a table with RLS enabled but zero SELECT policy
    written yet returns 0 rows for EVERYONE, attacker and rightful owner
    alike — indistinguishable from real isolation unless you also confirm
    the owner can see their own data.
    """
    cross_count, cross_err = _supabase_read_count(table, attacker_jwt, victim_tenant_id)
    if cross_err:
        return _result("supabase_direct", table, "read", "CHECK", cross_err)
 
    if cross_count > 0:
        return _result("supabase_direct", table, "read", "FAIL",
                        f"{cross_count} row(s) from tenant {victim_tenant_id} leaked")
 
    self_count, self_err = _supabase_read_count(table, attacker_jwt, attacker_tenant_id)
    if self_err:
        return _result("supabase_direct", table, "read", "CHECK",
                        f"0 rows cross-tenant, but control query failed: {self_err}")
 
    if self_count > 0:
        return _result("supabase_direct", table, "read", "PASS",
                        f"0 rows cross-tenant; {self_count} row(s) of own data confirmed readable "
                        f"— real isolation, not a blanket lockout")
 
    return _result("supabase_direct", table, "read", "CHECK",
                    "0 rows cross-tenant AND 0 rows for own tenant — can't confirm this is real "
                    "isolation vs. a table with no SELECT policy at all (locked for everyone, "
                    "owner included). Either insert a known row for this tenant and rerun, or "
                    "confirm via the Supabase Table Editor that a policy actually exists.")
 
 
def attack_supabase_write(table: str, attacker_jwt: str, payload: dict) -> dict:
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    try:
        resp = requests.post(
            url,
            headers={**supabase_headers(attacker_jwt), "Prefer": "return=representation"},
            json=payload,
            timeout=15,
        )
    except requests.RequestException as e:
        return _result("supabase_direct", table, "write", "CHECK", f"request error: {e}")
 
    if resp.status_code in (200, 201):
        return _result("supabase_direct", table, "write", "FAIL",
                        f"insert succeeded ({resp.status_code}): row written into victim tenant")
 
    body_text = resp.text.lower()
    if "row-level security" in body_text or "row level security" in body_text:
        return _result("supabase_direct", table, "write", "PASS",
                        f"blocked by RLS policy ({resp.status_code})")
 
    return _result("supabase_direct", table, "write", "CHECK",
                    f"insert blocked ({resp.status_code}), but not confirmed as "
                    f"an RLS block — read this before trusting it: {resp.text[:200]}")
 
 
# ---------------------------------------------------------------------------
# FastAPI attacks
# ---------------------------------------------------------------------------
 
def attack_fastapi_chat(victim_tenant_id: str, attacker_token: str | None) -> dict:
    """
    Calls POST /chat with the victim's tenant_id in the body.
    Before Thursday's auth wiring: no Authorization header at all — this is
    the exact reproduction of Mahi's Monday finding.
    After Thursday: pass --attacker-token so this becomes a real test of
    "does the backend still trust the body's tenant_id even with a valid
    token for a DIFFERENT tenant attached".
    """
    url = f"{FASTAPI_BASE_URL}/chat"
    headers = {"Content-Type": "application/json"}
    if attacker_token:
        headers["Authorization"] = f"Bearer {attacker_token}"
 
    payload = {
        "tenant_id": victim_tenant_id,
        "question": "ATTACK-TEST probe question — ignore if seen in real chat history",
        "top_k": 3,
    }
 
    # Render's free tier can take 30-50s to wake a cold instance (see Week 2/3
    # logs) — a single 30s timeout would misreport a sleeping backend as a
    # tool/network failure rather than an actual test result. Give it a long
    # first timeout, then one quick retry for a now-warm instance.
    resp = None
    last_err = None
    for attempt_timeout in (60, 20):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=attempt_timeout)
            break
        except requests.exceptions.Timeout as e:
            last_err = e
            continue
        except requests.RequestException as e:
            return _result("fastapi", "chat_sessions+messages", "read+write", "CHECK",
                            f"request error: {e}")
 
    if resp is None:
        return _result("fastapi", "chat_sessions+messages", "read+write", "CHECK",
                        f"timed out twice (60s cold-start attempt + 20s retry): {last_err} — "
                        f"backend may be down rather than just cold; check Render directly "
                        f"before assuming this is a cold-start")
 
    if resp.status_code in (401, 403):
        return _result("fastapi", "chat_sessions+messages", "read+write", "PASS",
                        f"rejected ({resp.status_code}) — auth check is working")
 
    if resp.status_code == 200:
        auth_note = "with attacker token for a DIFFERENT tenant" if attacker_token else "with NO auth at all"
        return _result("fastapi", "chat_sessions+messages", "read+write", "FAIL",
                        f"200 OK {auth_note} — got an answer, and a fake chat_session + "
                        f"messages row were almost certainly just written into tenant "
                        f"{victim_tenant_id}'s real data")
 
    return _result("fastapi", "chat_sessions+messages", "read+write", "CHECK",
                    f"unexpected status {resp.status_code}: {resp.text[:200]}")
 
 
# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
 
def _result(path, table, operation, status, detail) -> dict:
    return {"path": path, "table": table, "operation": operation,
            "status": status, "detail": detail}
 
 
def print_report(results: list[dict]):
    print()
    print(f"{'PATH':<16}{'TABLE':<20}{'OP':<10}{'STATUS':<8}DETAIL")
    print("-" * 100)
    for r in results:
        print(f"{r['path']:<16}{r['table']:<20}{r['operation']:<10}{r['status']:<8}{r['detail']}")
    print()
 
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    summary = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
    print(f"Summary — {summary}")
    for table, reason in SKIPPED.items():
        print(f"SKIPPED — {table}: {reason}")
    print()
 
 
def write_markdown_log(results: list[dict], path: str = "attack_log.md"):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"\n## Run — {ts}\n", "| Path | Table | Op | Status | Detail |",
             "|---|---|---|---|---|"]
    for r in results:
        detail = r["detail"].replace("|", "/")
        lines.append(f"| {r['path']} | {r['table']} | {r['operation']} | "
                      f"**{r['status']}** | {detail} |")
    for table, reason in SKIPPED.items():
        lines.append(f"| — | {table} | — | **SKIP** | {reason} |")
    lines.append("")
 
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Appended results to {path}")
 
 
# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
 
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attacker-token", default=None,
                         help="Tenant A's JWT to attach as Authorization header "
                              "on the FastAPI attack (use once auth is wired, Thursday+)")
    parser.add_argument("--read-only", action="store_true",
                         help="Skip the write/INSERT attacks (Supabase-direct path only)")
    parser.add_argument("--log-file", default="attack_log.md",
                         help="Markdown file to append results to")
    args = parser.parse_args()
 
    check_config()
 
    print("Logging in as Tenant A (attacker) and Tenant B (victim)...")
    tenant_a_jwt = get_jwt(TENANT_A_EMAIL, TENANT_A_PASSWORD)
    print("  Tenant A: OK")
    # Tenant B login isn't strictly needed for the attacks below (we already
    # know Tenant B's ID from config), but confirming the login works is a
    # cheap sanity check that the test account itself hasn't broken.
    get_jwt(TENANT_B_EMAIL, TENANT_B_PASSWORD)
    print("  Tenant B: OK")
 
    results = []
 
    print("\nRunning Supabase-direct READ attacks (Tenant A -> Tenant B's data, "
          "with an own-data control query)...")
    for table in READ_TEST_TABLES:
        results.append(attack_supabase_read(table, tenant_a_jwt, TENANT_A_ID, TENANT_B_ID))
 
    if not args.read_only:
        print("Running Supabase-direct WRITE attacks (Tenant A -> Tenant B's tables)...")
        payloads = _write_payloads(TENANT_B_ID)
        for table, payload in payloads.items():
            results.append(attack_supabase_write(table, tenant_a_jwt, payload))
    else:
        print("Skipping write attacks (--read-only)")
 
    print("Running FastAPI /chat attack (Tenant A -> Tenant B's tenant_id)...")
    results.append(attack_fastapi_chat(TENANT_B_ID, args.attacker_token))
 
    print_report(results)
    write_markdown_log(results, args.log_file)
 
 
if __name__ == "__main__":
    main()

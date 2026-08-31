"""
Per-tenant rate limiting for /chat.

Belongs in your backend, e.g. backend/rate_limit.py — server-side code,
not widget code.

WHY THIS EXISTS
----------------
tenant_id and the API base URL are BOTH necessarily public — the
widget runs inside every visitor's browser, so there's no way to hide
them, and that's fine on its own (see the "public identifier" note in
CORS-SETUP.md — this is the same pattern as a Stripe publishable key).

BUT nothing currently stops someone from scraping a tenant_id off a
tenant's public site and hitting /chat directly with a script — no
browser, no widget, no CORS involved at all. CORS only restricts what
JavaScript running IN A BROWSER can do; a plain Python script or a
curl loop is never subject to it. Every /chat call triggers a real
LLM API call, so unbounded requests are a real-money abuse vector —
not a data leak (RLS still protects the actual documents), a COST
one.

This caps requests per tenant_id in a SLIDING time window (not a
fixed one — a fixed window has a known edge case: 30 requests at
0:59 plus 30 more at 1:01 both pass their own window's check
individually, but that's 60 requests in ~2 real seconds).

KNOWN LIMITATION, on purpose, not hidden: this is in-memory, per
process. Fine on Render's free tier (one instance, one worker).
Will NOT work correctly across multiple server instances/workers —
each would keep its own separate counters, so the real limit becomes
(max_requests * number_of_instances). If this ever scales beyond one
instance, this needs to move to something shared (Redis, or a table
in Postgres) instead. This is not a security boundary — it's a cost
control. RLS is still what actually protects tenant data.
"""

import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import HTTPException

DEFAULT_MAX_REQUESTS = 30
DEFAULT_WINDOW_SECONDS = 60.0

# tenant_id -> deque of request timestamps within the current window
_request_log: dict[str, deque] = defaultdict(deque)


def enforce_chat_rate_limit(
    tenant_id: str,
    max_requests: int = DEFAULT_MAX_REQUESTS,
    window_seconds: float = DEFAULT_WINDOW_SECONDS,
    _now: Optional[float] = None,
) -> None:
    """Call this at the TOP of the /chat route, right after parsing
    the request body (so tenant_id is available), and BEFORE doing
    any real work — embedding the query, hitting pgvector, calling
    the LLM. Reject before spending money, not after.

    Raises HTTPException(429) if this tenant is over the limit.
    _now is an injection point for tests only — real callers should
    never pass it, it defaults to the real clock.
    """
    now = _now if _now is not None else time.monotonic()
    log = _request_log[tenant_id]

    # Drop timestamps that have aged out of the window.
    while log and now - log[0] > window_seconds:
        log.popleft()

    if len(log) >= max_requests:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Too many requests for this tenant. "
                f"Limit is {max_requests} per {window_seconds:.0f}s — "
                f"please slow down."
            ),
        )

    log.append(now)


def _reset_for_tests() -> None:
    """Test-only helper — clears all tenants' logs between test cases."""
    _request_log.clear()


# In main.py, inside the /chat route, as the very first line:
#
#   from rate_limit import enforce_chat_rate_limit
#
#   @app.post("/chat")
#   async def chat(request: ChatRequest):
#       enforce_chat_rate_limit(request.tenant_id)
#       ... existing embed -> retrieve -> generate logic ...

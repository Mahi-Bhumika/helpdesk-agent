"""
Smoke tests — not unit tests. These hit a REAL running instance of the app
(local uvicorn, docker run, or a deployed URL) over HTTP, exactly like the
Week 7 plan describes. They exist to catch "the app doesn't even boot / the
core path is broken" before anything deploys, not to test every edge case.

Run with:
    TEST_BASE_URL=http://localhost:8000 TEST_TENANT_ID=<real-uuid> pytest tests/ -v

⚠️ CHECK BEFORE RUNNING — I don't have your real main.py, so verify:
  1. You actually have a `/health` route. If not, add one (see note below).
  2. /chat's real auth: per your Week 4 log, /chat is protected by an
     Origin-header check against the tenant's `website_domain`, not a JWT
     (visitors don't log in). If that's still accurate, set TEST_ORIGIN
     below to match a real tenant's registered website_domain.
  3. The exact field names on ChatQuery / your /chat response — I'm using
     tenant_id/question/top_k and expecting an "answer" key back, per your
     Week 2 Day 13/14 code. Adjust if your model has since gained e.g.
     session_id.
"""

import os

import httpx
import pytest

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
TEST_TENANT_ID = os.getenv("TEST_TENANT_ID")  # a real tenant with real uploaded docs
TEST_ORIGIN = os.getenv("TEST_ORIGIN")  # must match that tenant's website_domain, if /chat checks Origin

pytestmark = pytest.mark.skipif(
    TEST_TENANT_ID is None,
    reason="TEST_TENANT_ID not set — smoke tests need a real, seeded tenant to hit /chat against",
)


def test_health():
    r = httpx.get(f"{BASE_URL}/health", timeout=10)
    assert r.status_code == 200


def test_tenants_rejects_incomplete_payload():
    # Contract check, not a real signup — confirms Pydantic validation is wired up.
    r = httpx.post(f"{BASE_URL}/tenants", json={}, timeout=10)
    assert r.status_code == 422


def test_chat_smoke():
    headers = {"Origin": TEST_ORIGIN} if TEST_ORIGIN else {}
    payload = {
        "tenant_id": TEST_TENANT_ID,
        "question": "What is this document about?",
        "top_k": 3,
    }
    r = httpx.post(f"{BASE_URL}/chat", json=payload, headers=headers, timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert "answer" in body or "retrieved_chunks" in body


def test_chat_rejects_unknown_tenant():
    payload = {
        "tenant_id": "00000000-0000-0000-0000-000000000000",
        "question": "hello",
        "top_k": 3,
    }
    r = httpx.post(f"{BASE_URL}/chat", json=payload, timeout=15)
    # Should NOT silently succeed with zero chunks and a 200 — pin down what
    # your actual behavior is (404? 200 with empty chunks?) and assert that,
    # not this guess.
    assert r.status_code in (200, 404)

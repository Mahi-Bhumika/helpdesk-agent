import os
import jwt
from jwt import PyJWKClient
from fastapi import Header, HTTPException, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db

SUPABASE_URL = os.getenv("SUPABASE_URL")  # e.g. https://oqtuxlpygpydojjwxyli.supabase.co
JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
_jwks_client = PyJWKClient(JWKS_URL)


def decode_jwt(authorization: str = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ", 1)[1]
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token, signing_key.key, algorithms=["ES256"], audience="authenticated"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload["sub"]


async def get_current_user(
    user_id: str = Depends(decode_jwt),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        text("SELECT tenant_id, status, role FROM users WHERE user_id = :user_id"),
        {"user_id": user_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=403, detail="User not found")
    if row.status != "active":
        raise HTTPException(status_code=403, detail="Account not active")
    return {"user_id": user_id, "tenant_id": str(row.tenant_id), "role": row.role}
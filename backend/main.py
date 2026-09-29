import asyncio
import difflib
import json
import os as os_module
import re
import tempfile
import time
from enum import Enum
from urllib.parse import urlparse

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import decode_jwt, get_current_user
from chunking import chunk_text, embed_chunks
from database import get_db
from extract_text import extract_text
from rate_limit import enforce_chat_rate_limit

groq_client = Groq(api_key=os_module.getenv("GROQ_API_KEY"))

app = FastAPI()

# --- CORS: Option A (wildcard) — confirmed as the shipped configuration. ---
# /chat and /kb/upload are protected by their own rate-limiting, Origin checks,
# and JWT/tenant scoping, so a permissive CORS layer here is an accepted tradeoff,
# not an oversight. Revisit only if credentialed cross-origin requests are ever needed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


# --- Pydantic model: defines the "shape" of a Document ---
class Document(BaseModel):
    id: int | None = None
    title: str
    content: str



@app.get("/")
def read_root():
    return {"status": "ok"}


@app.get("/documents/{document_id}")
async def get_document(
    document_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = text("SELECT * FROM documents WHERE document_id = :document_id")
    result = await db.execute(query, {"document_id": document_id})
    row = result.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found")
    doc = dict(row._mapping)
    if str(doc["tenant_id"]) != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    return doc


class DocumentUpdate(BaseModel):
    file_url: str | None = None
    format: str | None = None
    theme: str | None = None
    status: str | None = None


@app.put("/documents/{document_id}")
async def update_document(
    document_id: str,
    doc: DocumentUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        text("SELECT document_id, tenant_id FROM documents WHERE document_id = :document_id"),
        {"document_id": document_id}
    )
    row = existing.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if str(row.tenant_id) != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    query = text("""
        UPDATE documents
        SET file_url = COALESCE(:file_url, file_url),
            format = COALESCE(:format, format),
            theme = COALESCE(:theme, theme),
            status = COALESCE(:status, status)
        WHERE document_id = :document_id
        RETURNING document_id, tenant_id, file_url, format, theme, status, created_at
    """)
    result = await db.execute(query, {**doc.model_dump(), "document_id": document_id})
    await db.commit()
    return dict(result.fetchone()._mapping)

#deleting a document
@app.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        text("SELECT document_id, tenant_id FROM documents WHERE document_id = :document_id"),
        {"document_id": document_id}
    )
    row = existing.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if str(row.tenant_id) != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    # Delete child rows first, in dependency order — no ON DELETE CASCADE
    # confirmed at the schema level, so this is explicit rather than assumed.

    # message_sources references document_chunks.chunk_id — clear those first,
    # or deleting a chunk that was ever cited in a past chat answer would 409
    # on the foreign key.
    await db.execute(
        text("""
            DELETE FROM message_sources
            WHERE chunk_id IN (
                SELECT chunk_id FROM document_chunks WHERE document_id = :document_id
            )
        """),
        {"document_id": document_id},
    )

    # Now safe to delete the chunks themselves
    await db.execute(
        text("DELETE FROM document_chunks WHERE document_id = :document_id"),
        {"document_id": document_id},
    )

    # Finally the document row itself
    await db.execute(
        text("DELETE FROM documents WHERE document_id = :document_id"),
        {"document_id": document_id},
    )

    await db.commit()
    return {"status": "deleted", "document_id": document_id}

# POST — create a new document
class DocumentCreate(BaseModel):
    tenant_id: str
    uploaded_by: str | None = None
    file_url: str | None = None
    format: str | None = None
    theme: str | None = None


@app.post("/documents")
async def create_document(
    doc: DocumentCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if doc.tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    query = text("""
        INSERT INTO documents (tenant_id, uploaded_by, file_url, format, theme)
        VALUES (:tenant_id, :uploaded_by, :file_url, :format, :theme)
        RETURNING document_id, tenant_id, status, created_at
    """)
    result = await db.execute(query, {
        **doc.model_dump(),
        # server-derived from the verified JWT, never trusted from the client —
        # same pattern already used for tenant_id elsewhere in this file
        "uploaded_by": current_user["user_id"],
    })
    await db.commit()
    return dict(result.fetchone()._mapping)


@app.get("/db-check")
async def db_check(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT 1"))
    return {"database_connected": result.scalar() == 1}


# --- Pydantic model matching the tenants table ---
class TenantCreate(BaseModel):
    owner_id: str
    owner_email: str
    company_name: str
    type_of_business: str | None = None
    subscription_plan: str | None = None
    bot_name: str | None = None
    greeting_message: str | None = None
    theme_color: str | None = None
    fallback_message: str | None = None


@app.get("/tenants/{tenant_id}/widget-config")
async def get_widget_config(tenant_id: str, db: AsyncSession = Depends(get_db)):
    enforce_chat_rate_limit(f"widget-config:{tenant_id}", max_requests=60, window_seconds=60.0)

    result = await db.execute(
        text("""
            SELECT bot_name, greeting_message, theme_color, fallback_message
            FROM tenants
            WHERE tenant_id = :tenant_id
        """),
        {"tenant_id": tenant_id},
    )
    tenant = result.fetchone()

    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return {
        "bot_name": tenant.bot_name,
        "greeting_message": tenant.greeting_message,
        "theme_color": tenant.theme_color,
        "fallback_message": tenant.fallback_message,
    }


@app.post("/tenants")
async def create_tenant(
    tenant: TenantCreate,
    verified_user_id: str = Depends(decode_jwt),
    db: AsyncSession = Depends(get_db),
):
    if tenant.owner_id != verified_user_id:
        raise HTTPException(status_code=403, detail="owner_id does not match authenticated user")

    tenant_query = text("""
    INSERT INTO tenants (
        company_name, type_of_business, subscription_plan,
        bot_name, greeting_message, theme_color, fallback_message
    )
    VALUES (
        :company_name, :type_of_business, :subscription_plan,
        :bot_name, :greeting_message, :theme_color, :fallback_message
    )
    RETURNING tenant_id, company_name, invite_token, created_at
""")
    tenant_data = tenant.model_dump(exclude={"owner_id", "owner_email"})
    result = await db.execute(tenant_query, tenant_data)
    new_tenant = result.fetchone()

    user_query = text("""
        INSERT INTO users (user_id, tenant_id, email, password_hash, role)
        VALUES (:user_id, :tenant_id, :email, :password_hash, 'owner')
    """)
    await db.execute(user_query, {
        "user_id": tenant.owner_id,
        "tenant_id": new_tenant.tenant_id,
        "email": tenant.owner_email,
        "password_hash": "MANAGED_BY_SUPABASE_AUTH",
        "name": new_tenant.company_name
    })
    await db.commit()
    return dict(new_tenant._mapping)

MAX_CHUNKS_PER_UPLOAD = 65


@app.post("/kb/upload")
async def upload_document(
    document_id: str = Form(...),
    tenant_id: str = Form(...),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if tenant_id != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    # Flip to 'processing' immediately, committed on its own — this is the
    # real status while parsing/chunking/embedding are running, rather than
    # jumping straight from 'uploaded' to 'ready'/'failed' with a long silent
    # gap. Uploaded (POST /documents) -> Processing (this line) -> Ready/Failed.
    await db.execute(
        text("UPDATE documents SET status = 'processing' WHERE document_id = :document_id"),
        {"document_id": document_id},
    )
    await db.commit()

    # Save the uploaded file to a temp path so pdfplumber can read it
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        contents = await file.read()
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        t0 = time.time()
        try:
            extracted_text = await asyncio.to_thread(extract_text, tmp_path)
        except ValueError as e:
            # extract_text() raises ValueError for two distinct real failures:
            # a corrupted/unreadable PDF, or a fully-scanned document with zero
            # extractable text on any page. Both are genuine upload failures,
            # not a 500 — surface them clearly and mark the document as failed
            # instead of letting an unhandled exception fall through.
            await db.execute(
                text("UPDATE documents SET status = 'failed' WHERE document_id = :document_id"),
                {"document_id": document_id},
            )
            await db.commit()
            raise HTTPException(status_code=422, detail=str(e))
        print(f"extract_text took {time.time() - t0:.2f}s")

        t1 = time.time()
        chunks = await asyncio.to_thread(chunk_text, extracted_text, chunk_size=250, overlap=40)
        print(f"chunk_text took {time.time() - t1:.2f}s")

        if len(chunks) > MAX_CHUNKS_PER_UPLOAD:
            await db.execute(
                text("""
                    UPDATE documents
                    SET status = 'failed'
                    WHERE document_id = :document_id
                """),
                {"document_id": document_id},
            )
            await db.commit()
            raise HTTPException(
                status_code=422,
                detail=(
                    f"This document produced {len(chunks)} chunks, which exceeds the "
                    f"{MAX_CHUNKS_PER_UPLOAD}-chunk limit per upload. Try splitting it into "
                    f"smaller documents and uploading each separately."
                ),
            )

        t2 = time.time()
        embeddings = await asyncio.to_thread(embed_chunks, chunks)
        print(f"embed_chunks took {time.time() - t2:.2f}s")

        insert_query = text("""
            INSERT INTO document_chunks (document_id, tenant_id, chunk_text, embedding, chunk_index)
            VALUES (:document_id, :tenant_id, :chunk_text, :embedding, :chunk_index)
        """)

        rows = [
            {
                "document_id": document_id,
                "tenant_id": tenant_id,
                "chunk_text": chunk,
                "embedding": str(emb),
                "chunk_index": idx,
            }
            for idx, (chunk, emb) in enumerate(zip(chunks, embeddings))
        ]

        await db.execute(insert_query, rows)

        # Mark the document ready in the SAME transaction as the chunk inserts,
        # so status only ever reflects reality — this update was missing
        # entirely before, leaving every successful upload's status stuck
        # wherever it started (e.g. permanently 'uploading').
        await db.execute(
            text("UPDATE documents SET status = 'ready' WHERE document_id = :document_id"),
            {"document_id": document_id},
        )
        await db.commit()

    finally:
        os_module.remove(tmp_path)

    return {
        "document_id": document_id,
        "chunks_inserted": len(chunks),
    }

def extract_origin(url_or_domain: str) -> str:
    """Normalizes domain or full URL down to scheme://host."""
    if not url_or_domain:
        return ""
    if not url_or_domain.startswith(("http://", "https://")):
        url_or_domain = "https://" + url_or_domain
    parsed = urlparse(url_or_domain)
    return f"{parsed.scheme}://{parsed.netloc}"


# ============================================================
# RAG CHAT PIPELINE
# Replace your existing classification/retrieval + /chat code
# with this entire block.
# ============================================================

import re
import difflib
from typing import Optional

from fastapi import HTTPException, Header, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# ============================================================
# 1. SMALLTALK PATTERNS
# ============================================================

_GREETING_PATTERN = re.compile(
    r"^\s*(h+i+|h+e+y+|hello+|heya+|howdy+|hola+|y+o+|sup|"
    r"good\s+(morning|afternoon|evening))\b",
    re.IGNORECASE,
)

_ACKNOWLEDGMENT_PATTERN = re.compile(
    r"^\s*(thanks?|thank\s*you+|thx|ty|tysm|ok(?:ay)?|okie|"
    r"got\s*it|cool|great|perfect|alright|sounds\s+good|"
    r"awesome|nice|sure|no\s+problem|np)\b",
    re.IGNORECASE,
)

_IDENTITY_STATUS_PATTERN = re.compile(
    r"^\s*(who\s+are\s+you|what\s+are\s+you|are\s+you\s+a\s+bot|"
    r"how\s+are\s+you|what\s+is\s+your\s+name)\b",
    re.IGNORECASE,
)

_GREETING_WORDS = [
    "hi",
    "hii",
    "hiii",
    "hey",
    "heyy",
    "heyyy",
    "heya",
    "hello",
    "helloo",
    "howdy",
    "hola",
    "yo",
    "yoo",
    "sup",
    "gm",
]

_ACK_WORDS = [
    "thanks",
    "thankyou",
    "thank you",
    "thx",
    "ty",
    "tysm",
    "ok",
    "okay",
    "okie",
    "got it",
    "cool",
    "great",
    "perfect",
    "alright",
    "sounds good",
    "awesome",
    "nice",
    "sure",
    "no problem",
    "np",
]

_IDENTITY_PHRASES = [
    "who are you",
    "what are you",
    "are you a bot",
    "how are you",
    "what is your name",
]


def _fuzzy_match(
    token: str,
    candidates: list[str],
    cutoff: float = 0.72,
) -> bool:
    if not token:
        return False

    if token in candidates:
        return True

    return bool(
        difflib.get_close_matches(
            token,
            candidates,
            n=1,
            cutoff=cutoff,
        )
    )


def classify_smalltalk(
    question: str,
    has_history: bool = False,
) -> tuple[str, str] | None:

    raw = question.strip()

    if not raw:
        return None

    word_count = len(raw.split())

    # Never classify long questions as smalltalk.
    if word_count > 5:
        return None

    if _IDENTITY_STATUS_PATTERN.search(raw):
        return (
            "identity",
            "I am an AI support assistant here to help answer your questions.",
        )

    if _GREETING_PATTERN.search(raw):
        return (
            "greeting",
            "greeting_placeholder",
        )

    if _ACKNOWLEDGMENT_PATTERN.search(raw):
        return (
            "acknowledgment",
            "You're welcome! Let me know if there's anything else I can help with.",
        )

    if word_count <= 3:

        normalized = re.sub(
            r"[^a-z\s]",
            "",
            raw.lower(),
        ).strip()

        normalized = re.sub(
            r"\s+",
            " ",
            normalized,
        )

        if not normalized:
            return None

        first_word = normalized.split()[0]

        if _fuzzy_match(
            normalized,
            _IDENTITY_PHRASES,
            cutoff=0.80,
        ):
            return (
                "identity",
                "I am an AI support assistant here to help answer your questions.",
            )

        if (
            _fuzzy_match(
                first_word,
                _GREETING_WORDS,
                cutoff=0.72,
            )
            or normalized in [
                "good morning",
                "good afternoon",
                "good evening",
            ]
        ):
            return (
                "greeting",
                "greeting_placeholder",
            )

        if (
            _fuzzy_match(
                normalized,
                _ACK_WORDS,
                cutoff=0.75,
            )
            or _fuzzy_match(
                first_word,
                _ACK_WORDS,
                cutoff=0.75,
            )
        ):
            return (
                "acknowledgment",
                "You're welcome! Let me know if there's anything else I can help with.",
            )

    return None


# ============================================================
# 2. QUERY TYPE DETECTION
# ============================================================

_ENUMERATION_PATTERN = re.compile(
    r"\b("
    r"list\s+(?:of\s+)?(?:all|everything)|"
    r"full\s+list|"
    r"complete\s+list|"
    r"all\s+(?:of\s+)?(?:the\s+|your\s+)?"
    r"(?:products|services|items|things)|"
    r"what\s+(?:services|products|items)\s+do\s+you\s+"
    r"(?:offer|have|sell)|"
    r"everything\s+you\s+(?:offer|have|sell)|"
    r"catalog|"
    r"show\s+(?:me\s+)?(?:all|everything)|"
    r"what\s+do\s+you\s+(?:offer|sell|have)|"
    r"what\s+all\s+(?:do\s+you\s+)?(?:have|offer|sell)|"
    r"what\s+are\s+(?:your|the)\s+products"
    r")\b",
    re.IGNORECASE,
)


_SUMMARY_PATTERN = re.compile(
    r"\b("
    r"summar(?:y|ise|ize)|"
    r"overview|"
    r"recap|"
    r"tl;?dr|"
    r"brief(?:ly)?|"
    r"give\s+me\s+the\s+gist"
    r")\b",
    re.IGNORECASE,
)


_PRICE_PATTERN = re.compile(
    r"\b("
    r"price|"
    r"prices|"
    r"pricing|"
    r"cost|"
    r"costs|"
    r"expensive|"
    r"cheap|"
    r"cheapest|"
    r"least\s+expensive|"
    r"most\s+expensive|"
    r"costliest|"
    r"how\s+much|"
    r"worth"
    r")\b",
    re.IGNORECASE,
)


_COMPARISON_PATTERN = re.compile(
    r"\b("
    r"compare|"
    r"comparison|"
    r"versus|"
    r"\bvs\b|"
    r"difference|"
    r"better|"
    r"best|"
    r"worst|"
    r"higher|"
    r"lower|"
    r"maximum|"
    r"minimum|"
    r"largest|"
    r"smallest|"
    r"highest|"
    r"lowest|"
    r"least|"
    r"most"
    r")\b",
    re.IGNORECASE,
)


_RANKING_PATTERN = re.compile(
    r"\b("
    r"rank|"
    r"ranking|"
    r"order\s+(?:the\s+)?products|"
    r"sort\s+(?:the\s+)?products|"
    r"top\s+\d+|"
    r"which\s+is\s+(?:the\s+)?(?:best|worst|cheapest|most\s+expensive)|"
    r"which\s+product"
    r")\b",
    re.IGNORECASE,
)


_RECOMMENDATION_PATTERN = re.compile(
    r"\b("
    r"should\s+i\s+buy|"
    r"should\s+i\s+get|"
    r"should\s+i\s+choose|"
    r"recommend|"
    r"recommendation|"
    r"which\s+should\s+i|"
    r"what\s+should\s+i\s+buy|"
    r"is\s+it\s+worth|"
    r"worth\s+buying|"
    r"good\s+choice"
    r")\b",
    re.IGNORECASE,
)


_CONTINUATION_TRIGGERS = [
    "and",
    "and?",
    "anything else",
    "any other",
    "any others",
    "others",
    "other options",
    "what else",
    "more options",
    "any more",
    "is that all",
    "is that it",
    "thats it",
    "that's it",
    "what about the rest",
    "more",
]


def is_enumeration_query(question: str) -> bool:
    return bool(_ENUMERATION_PATTERN.search(question))


def is_summary_query(question: str) -> bool:
    return bool(_SUMMARY_PATTERN.search(question))


def is_price_query(question: str) -> bool:
    return bool(_PRICE_PATTERN.search(question))


def is_comparison_query(question: str) -> bool:
    return bool(_COMPARISON_PATTERN.search(question))


def is_ranking_query(question: str) -> bool:
    return bool(_RANKING_PATTERN.search(question))


def is_recommendation_query(question: str) -> bool:
    return bool(_RECOMMENDATION_PATTERN.search(question))


def is_continuation_query(question: str) -> bool:
    q = question.strip().lower().rstrip("?!.,")

    if not q:
        return False

    if len(q.split()) > 6:
        return False

    return (
        q == "and"
        or any(
            q == trigger.rstrip("?!.")
            for trigger in _CONTINUATION_TRIGGERS
        )
    )


# ============================================================
# 3. FOLLOW-UP / QUERY REWRITE
# ============================================================

_FOLLOWUP_TRIGGERS = [
    "tell me more",
    "more details",
    "how much",
    "price",
    "cost",
    "and the other",
    "what about",
    "the other one",
    "both",
    "this",
    "that",
    "these",
    "those",
    "it",
    "its",
    "their",
    "them",
    "how much is it",
    "why",
    "where",
    "can i get",
    "is it available",
    "how do i",
    "any other",
    "other options",
    "what else",
    "anything else",
    "more",
    "others",
    "least expensive",
    "most expensive",
    "costliest",
    "cheapest",
]


def _needs_query_rewrite(
    question: str,
    history_rows: list,
) -> bool:

    if not history_rows:
        return False

    q = question.strip().lower()

    # Short questions are almost always potentially contextual.
    if len(q.split()) <= 8:
        return True

    return any(
        trigger in q
        for trigger in _FOLLOWUP_TRIGGERS
    )


def _rewrite_query_for_retrieval(
    question: str,
    history_rows: list,
) -> str:

    history_str = "\n".join(
        [
            (
                f"{'User' if getattr(h, 'sender', '') == 'user' else 'Assistant'}: "
                f"{getattr(h, 'content', '')}"
            )
            for h in history_rows[-8:]
        ]
    )

    rewrite_prompt = [
        {
            "role": "system",
            "content": """
You are a search-query reformulation module for a business RAG chatbot.

Your job is to convert a user's follow-up question into a standalone retrieval query.

Use the conversation history to resolve:
- it
- this
- that
- those
- them
- its
- their
- the other one
- the product
- the catalog
- prices
- rankings
- comparisons

IMPORTANT:
Preserve the user's actual intent.

Examples:

User: "what are the products?"
Follow-up: "which is cheapest?"
Output:
"which product is the cheapest by price in the product catalog"

User: "what are the products?"
Follow-up: "price of luminamist"
Output:
"price of LuminaMist Diffuser"

User: "what are the products?"
Follow-up: "rank them"
Output:
"rank the products in the catalog using the available product information"

User: "tell me about AetherVane 500"
Follow-up: "what about its price?"
Output:
"price of AetherVane 500"

User: "what is AetherVane 500?"
Follow-up: "is it worth buying?"
Output:
"whether AetherVane 500 is worth buying based on its documented features, specifications, and price"

Do NOT answer the question.

Output ONLY the standalone search query.
""",
        },
        {
            "role": "user",
            "content": (
                f"Conversation History:\n{history_str}\n\n"
                f"Current User Question:\n{question}\n\n"
                "Standalone Search Query:"
            ),
        },
    ]

    try:

        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=rewrite_prompt,
            temperature=0.0,
            max_tokens=100,
        )

        rewritten = (
            response.choices[0]
            .message.content
            .strip()
            .strip('"')
            .strip()
        )

        if rewritten:
            return rewritten

    except Exception as e:
        print(
            f"[DEBUG] Query rewrite failed: {e}"
        )

    return question


# ============================================================
# 4. QUERY CONFIGURATION
# ============================================================

NORMAL_TOP_K = 8
NORMAL_THRESHOLD = 0.25

# Broad retrieval for catalog/comparison questions.
WIDE_TOP_K = 30
WIDE_THRESHOLD = 0.12

# Very broad retrieval for catalog-wide questions.
CATALOG_TOP_K = 50
CATALOG_THRESHOLD = 0.08


# ============================================================
# 5. REQUEST / RESPONSE MODELS
# ============================================================

class ChatQuery(BaseModel):
    tenant_id: str
    session_id: str | None = None
    question: str
    top_k: int = 5


class ChatSource(BaseModel):
    chunk_id: str
    relevance_score: float


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    sources: list[ChatSource]


# ============================================================
# 6. MAIN CHAT ENDPOINT
# ============================================================

@app.post(
    "/chat",
    response_model=ChatResponse,
)
async def chat(
    query: ChatQuery,
    origin: str = Header(None),
    db: AsyncSession = Depends(get_db),
):

    enforce_chat_rate_limit(
        query.tenant_id
    )

    top_k = min(
        max(query.top_k, 1),
        10,
    )

    # --------------------------------------------------------
    # A. TENANT
    # --------------------------------------------------------

    tenant_row = await db.execute(
        text(
            """
            SELECT
                website_domain,
                fallback_message,
                bot_name,
                greeting_message
            FROM tenants
            WHERE tenant_id =
                CAST(:tid AS uuid)
            """
        ),
        {
            "tid": query.tenant_id
        },
    )

    tenant = tenant_row.fetchone()

    if (
        not tenant
        or not tenant.website_domain
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Tenant not configured "
                "for widget access"
            ),
        )

    if (
        not origin
        or extract_origin(
            tenant.website_domain
        ) != origin
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Origin not authorized "
                "for this tenant"
            ),
        )

    # --------------------------------------------------------
    # B. SESSION
    # --------------------------------------------------------

    session_id = query.session_id

    if session_id:

        existing_session = await db.execute(
            text(
                """
                SELECT session_id
                FROM chat_sessions
                WHERE session_id =
                    CAST(:sid AS uuid)
                AND tenant_id =
                    CAST(:tid AS uuid)
                """
            ),
            {
                "sid": session_id,
                "tid": query.tenant_id,
            },
        )

        if not existing_session.fetchone():
            session_id = None

    if not session_id:

        session_result = await db.execute(
            text(
                """
                INSERT INTO chat_sessions (
                    tenant_id
                )
                VALUES (
                    CAST(:tenant_id AS uuid)
                )
                RETURNING session_id
                """
            ),
            {
                "tenant_id": query.tenant_id
            },
        )

        session_id = str(
            session_result.fetchone().session_id
        )

    # --------------------------------------------------------
    # C. HISTORY
    # --------------------------------------------------------

    history_result = await db.execute(
        text(
            """
            SELECT
                sender,
                content
            FROM messages
            WHERE session_id =
                CAST(:session_id AS uuid)
            ORDER BY created_at DESC
            LIMIT 8
            """
        ),
        {
            "session_id": session_id
        },
    )

    history_rows = list(
        reversed(
            history_result.fetchall()
        )
    )

    # --------------------------------------------------------
    # D. SMALLTALK
    # --------------------------------------------------------

    smalltalk_match = classify_smalltalk(
        query.question,
        has_history=bool(history_rows),
    )

    if smalltalk_match:

        kind, canned_reply = smalltalk_match

        if kind == "greeting":

            reply = (
                tenant.greeting_message
                or "Hello! How can I help you today?"
            )

        else:
            reply = canned_reply

        await db.execute(
            text(
                """
                INSERT INTO messages (
                    session_id,
                    tenant_id,
                    sender,
                    content
                )
                VALUES (
                    CAST(:session_id AS uuid),
                    CAST(:tenant_id AS uuid),
                    'user',
                    :content
                )
                """
            ),
            {
                "session_id": session_id,
                "tenant_id": query.tenant_id,
                "content": query.question,
            },
        )

        await db.execute(
            text(
                """
                INSERT INTO messages (
                    session_id,
                    tenant_id,
                    sender,
                    content
                )
                VALUES (
                    CAST(:session_id AS uuid),
                    CAST(:tenant_id AS uuid),
                    'bot',
                    :content
                )
                """
            ),
            {
                "session_id": session_id,
                "tenant_id": query.tenant_id,
                "content": reply,
            },
        )

        await db.commit()

        return ChatResponse(
            session_id=str(session_id),
            answer=reply,
            sources=[],
        )

    # --------------------------------------------------------
    # E. CLASSIFY QUERY
    # --------------------------------------------------------

    is_enum = is_enumeration_query(
        query.question
    )

    is_summary = is_summary_query(
        query.question
    )

    is_price = is_price_query(
        query.question
    )

    is_comparison = is_comparison_query(
        query.question
    )

    is_ranking = is_ranking_query(
        query.question
    )

    is_recommendation = is_recommendation_query(
        query.question
    )

    is_continuation = is_continuation_query(
        query.question
    )

    # --------------------------------------------------------
    # F. REWRITE FOLLOW-UPS
    # --------------------------------------------------------

    retrieval_query_text = query.question

    if _needs_query_rewrite(
        query.question,
        history_rows,
    ):

        retrieval_query_text = (
            _rewrite_query_for_retrieval(
                query.question,
                history_rows,
            )
        )

        print(
            "[DEBUG] Rewritten query: "
            f"'{retrieval_query_text}'"
        )

    # --------------------------------------------------------
    # G. RETRIEVAL MODE
    # --------------------------------------------------------

    catalog_wide_query = (
        is_enum
        or is_summary
        or is_ranking
        or is_comparison
        or is_price
        or is_continuation
    )

    if catalog_wide_query:

        effective_top_k = max(
            WIDE_TOP_K,
            top_k,
        )

        effective_threshold = (
            WIDE_THRESHOLD
        )

    else:

        effective_top_k = top_k

        effective_threshold = (
            NORMAL_THRESHOLD
        )

    # Catalog-wide requests get an especially large search.
    if is_enum or is_summary:

        effective_top_k = (
            CATALOG_TOP_K
        )

        effective_threshold = (
            CATALOG_THRESHOLD
        )

    # --------------------------------------------------------
    # H. EMBEDDING
    # --------------------------------------------------------

    query_embedding = embed_chunks(
        [retrieval_query_text]
    )[0]

    # --------------------------------------------------------
    # I. VECTOR SEARCH
    # --------------------------------------------------------

    search_query = text(
        """
        SELECT
            chunk_id,
            chunk_text,
            chunk_index,
            document_id,
            embedding <=> :query_embedding AS distance
        FROM document_chunks
        WHERE tenant_id =
            CAST(:tenant_id AS uuid)
        ORDER BY
            embedding <=> :query_embedding
        LIMIT :top_k
        """
    )

    result = await db.execute(
        search_query,
        {
            "query_embedding": str(
                query_embedding
            ),
            "tenant_id": query.tenant_id,
            "top_k": effective_top_k,
        },
    )

    rows = result.fetchall()

    # --------------------------------------------------------
    # J. THRESHOLD FILTERING
    # --------------------------------------------------------

    retrieved_chunks = [
        dict(row._mapping)
        for row in rows
        if (
            1 - row.distance
        ) >= effective_threshold
    ]

    # --------------------------------------------------------
    # K. SAFETY FALLBACK
    # --------------------------------------------------------
    #
    # If nothing cleared the threshold, keep the strongest
    # result if it is at least somewhat relevant.
    #
    # This prevents:
    #
    # "what is LuminaMist?"
    #
    # from becoming a fallback simply because its similarity
    # happened to be 0.22.
    # --------------------------------------------------------

    if (
        not retrieved_chunks
        and rows
    ):

        best = rows[0]

        best_similarity = (
            1 - best.distance
        )

        if best_similarity >= 0.18:

            retrieved_chunks = [
                dict(best._mapping)
            ]

            print(
                "[DEBUG] Relaxed retrieval "
                f"accepted similarity="
                f"{best_similarity:.3f}"
            )

    # --------------------------------------------------------
    # L. BUILD CONTEXT
    # --------------------------------------------------------

    if retrieved_chunks:

        context_parts = []

        for index, chunk in enumerate(
            retrieved_chunks,
            start=1,
        ):

            context_parts.append(
                (
                    f"[SOURCE {index}]\n"
                    f"{chunk['chunk_text']}"
                )
            )

        context = "\n\n---\n\n".join(
            context_parts
        )

    else:

        context = (
            "NO_RELEVANT_CONTEXT_FOUND"
        )

    fallback_text = (
        tenant.fallback_message
        or (
            "Sorry, I don't have an answer "
            "for that — try rephrasing or "
            "contact support."
        )
    )

    # --------------------------------------------------------
    # M. SPECIAL "ANYTHING ELSE" CHECK
    # --------------------------------------------------------

    no_more_items = False

    if (
        is_continuation
        and history_rows
    ):

        prior_sources_result = (
            await db.execute(
                text(
                    """
                    SELECT DISTINCT
                        ms.chunk_id
                    FROM message_sources ms
                    JOIN messages m
                        ON m.message_id =
                           ms.message_id
                    WHERE m.session_id =
                        CAST(:session_id AS uuid)
                    """
                ),
                {
                    "session_id": session_id
                },
            )
        )

        already_cited_ids = {
            str(r.chunk_id)
            for r in (
                prior_sources_result.fetchall()
            )
        }

        retrieved_ids = {
            str(chunk["chunk_id"])
            for chunk in retrieved_chunks
        }

        new_chunk_ids = (
            retrieved_ids
            - already_cited_ids
        )

        no_more_items = (
            bool(already_cited_ids)
            and not new_chunk_ids
        )

    # --------------------------------------------------------
    # N. SYSTEM PROMPT
    # --------------------------------------------------------

    bot_name = (
        tenant.bot_name
        or "a helpful AI assistant"
    )

    if no_more_items:

        system_prompt = f"""
You are {bot_name}, a support assistant for this business.

The user is asking whether there is anything else beyond what was already discussed.

The retrieved information contains no additional relevant products or information.

Reply with one short, natural sentence saying that this is everything currently available in the relevant category.

Do not invent anything.
Do not apologize.
Do not say you cannot understand.
"""

    else:

        system_prompt = f"""
You are {bot_name}, a support assistant for this business.

Your job is to answer the user's question using the retrieved business information.

IMPORTANT KNOWLEDGE RULE:
You may ONLY use factual information explicitly present in the Retrieved Context.

Conversation history may be used to resolve references such as:
- it
- this
- that
- its
- their
- them
- the product
- the other one

But conversation history is NOT an independent source of facts.

Do NOT invent prices.
Do NOT invent product specifications.
Do NOT invent product names.
Do NOT invent rankings.
Do NOT invent recommendations.
Do NOT assume that one product is better than another unless the retrieved information supports the comparison.

============================================================
QUERY-SPECIFIC BEHAVIOR
============================================================

1. PRODUCT / CATALOG QUESTIONS

If the user asks for products, offerings, or the catalog:

Return all relevant products found in the Retrieved Context.

Use bullet points.

Do not arbitrarily omit relevant products.

------------------------------------------------------------

2. SUMMARY QUESTIONS

If the user asks to summarize, give an overview, recap, or TL;DR:

Create a concise summary using the relevant information from the Retrieved Context.

Include the important products, features, specifications, prices, or other facts that are actually present.

Do not reduce the answer to only the first retrieved chunk.

------------------------------------------------------------

3. PRICE QUESTIONS

If the user asks for:
- a price
- prices
- cost
- cheapest
- least expensive
- most expensive
- costliest
- how much

Search the ENTIRE Retrieved Context for price information.

If multiple products have prices, compare them when the user asks for cheapest or most expensive.

If the requested product's price is present, give it.

If its price is NOT present, say that the price is not available in the retrieved catalog information.

Do NOT guess.

------------------------------------------------------------

4. COMPARISON QUESTIONS

If the user asks which product is:
- cheapest
- most expensive
- best
- worst
- largest
- smallest
- highest
- lowest
- maximum
- minimum
- better

Compare the relevant products using ONLY attributes explicitly present in the Retrieved Context.

For example:

If the user asks:
"which is the least expensive?"

Compare the documented prices.

If the user asks:
"which has the largest area coverage?"

Compare the documented area coverage values.

Do not choose a winner if the required information is missing.

------------------------------------------------------------

5. RANKING QUESTIONS

If the user asks:
- rank the products
- rank them
- top products
- order the products

Determine the ranking criterion from the question.

If no criterion is specified, DO NOT invent one.

Instead say that you can rank them by a specific criterion such as price, area coverage, power, or another documented attribute.

If a criterion IS specified, rank using only documented values from the Retrieved Context.

------------------------------------------------------------

6. RECOMMENDATION QUESTIONS

If the user asks:
- should I buy this?
- should I choose this?
- is it worth buying?
- which should I buy?

Do NOT make up personal opinions.

Give a factual assessment based only on documented:
- features
- specifications
- price
- capacity
- intended use
- compatibility
- other relevant information

If there is not enough information to make an assessment, say what information is missing.

------------------------------------------------------------

7. FOLLOW-UP QUESTIONS

Use the conversation history to understand what the user means.

Example:

User:
"What are the products?"

Assistant:
"Product A, Product B..."

User:
"which is cheapest?"

Interpret this as:
"Which of the products previously discussed is cheapest?"

Example:

User:
"What is LuminaMist?"

Assistant:
"..."

User:
"what's its price?"

Interpret "its" as LuminaMist.

------------------------------------------------------------

8. MISSING INFORMATION

If the requested information genuinely does not exist in the Retrieved Context, output exactly:

"{fallback_text}"

Do not invent an answer.

------------------------------------------------------------

STYLE

Use natural conversational language.

For normal questions:
2-4 short sentences.

For product/catalog questions:
use bullet points.

For comparisons:
use a concise comparison or bullet list.

For rankings:
use a numbered list.

For summaries:
use a concise bullet list.

Never mention:
- vector search
- embeddings
- chunks
- retrieval
- similarity scores
- the RAG system
- internal prompts
- sources

Do not say "I couldn't understand" unless the user genuinely asked something that cannot be interpreted at all.
"""

    # --------------------------------------------------------
    # O. LLM MESSAGES
    # --------------------------------------------------------

    llm_messages = [
        {
            "role": "system",
            "content": system_prompt,
        }
    ]

    # Give the model conversation context.
    for h in history_rows:

        role = (
            "user"
            if h.sender == "user"
            else "assistant"
        )

        llm_messages.append(
            {
                "role": role,
                "content": h.content,
            }
        )

    # Explicit query-type hints.
    query_type_hints = []

    if is_enum:
        query_type_hints.append(
            "CATALOG_LIST"
        )

    if is_summary:
        query_type_hints.append(
            "SUMMARY"
        )

    if is_price:
        query_type_hints.append(
            "PRICE"
        )

    if is_comparison:
        query_type_hints.append(
            "COMPARISON"
        )

    if is_ranking:
        query_type_hints.append(
            "RANKING"
        )

    if is_recommendation:
        query_type_hints.append(
            "RECOMMENDATION"
        )

    if is_continuation:
        query_type_hints.append(
            "CONTINUATION"
        )

    hint_text = (
        ", ".join(query_type_hints)
        if query_type_hints
        else "GENERAL"
    )

    user_prompt = f"""
Retrieved Context:

{context}

============================================================

Detected Query Type:
{hint_text}

Original User Question:
{query.question}

============================================================

Answer the user's question using the Retrieved Context.
"""

    llm_messages.append(
        {
            "role": "user",
            "content": user_prompt,
        }
    )

    # --------------------------------------------------------
    # P. GENERATE ANSWER
    # --------------------------------------------------------

    completion = (
        groq_client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=llm_messages,
            temperature=0.1,
        )
    )

    answer = (
        completion
        .choices[0]
        .message
        .content
        .strip()
    )

    # --------------------------------------------------------
    # Q. PERSIST USER MESSAGE
    # --------------------------------------------------------

    await db.execute(
        text(
            """
            INSERT INTO messages (
                session_id,
                tenant_id,
                sender,
                content
            )
            VALUES (
                CAST(:session_id AS uuid),
                CAST(:tenant_id AS uuid),
                'user',
                :content
            )
            """
        ),
        {
            "session_id": session_id,
            "tenant_id": query.tenant_id,
            "content": query.question,
        },
    )

    # --------------------------------------------------------
    # R. PERSIST BOT MESSAGE
    # --------------------------------------------------------

    bot_message_result = await db.execute(
        text(
            """
            INSERT INTO messages (
                session_id,
                tenant_id,
                sender,
                content
            )
            VALUES (
                CAST(:session_id AS uuid),
                CAST(:tenant_id AS uuid),
                'bot',
                :content
            )
            RETURNING message_id
            """
        ),
        {
            "session_id": session_id,
            "tenant_id": query.tenant_id,
            "content": answer,
        },
    )

    bot_message_id = (
        bot_message_result
        .fetchone()
        .message_id
    )

    # --------------------------------------------------------
    # S. STORE SOURCES
    # --------------------------------------------------------

    sources = []

    answer_is_fallback = (
        answer.strip()
        == fallback_text.strip()
    )

    if (
        retrieved_chunks
        and not answer_is_fallback
        and not no_more_items
    ):

        source_rows = []

        for chunk in retrieved_chunks:

            source_rows.append(
                {
                    "message_id": bot_message_id,
                    "chunk_id": chunk["chunk_id"],
                    "relevance_score": (
                        1 - chunk["distance"]
                    ),
                }
            )

        await db.execute(
            text(
                """
                INSERT INTO message_sources (
                    message_id,
                    chunk_id,
                    relevance_score
                )
                VALUES (
                    :message_id,
                    :chunk_id,
                    :relevance_score
                )
                """
            ),
            source_rows,
        )

        sources = [
            ChatSource(
                chunk_id=str(
                    row["chunk_id"]
                ),
                relevance_score=float(
                    row["relevance_score"]
                ),
            )
            for row in source_rows
        ]

    # --------------------------------------------------------
    # T. COMMIT
    # --------------------------------------------------------

    await db.commit()

    return ChatResponse(
        session_id=str(session_id),
        answer=answer,
        sources=sources,
    )


# ============================================================
# END CHAT
# IMPORTANT:
# Keep ONLY ONE EndChatRequest and ONE /chat/end endpoint.
# ============================================================

class EndChatRequest(BaseModel):
    session_id: str
    tenant_id: str
    csat: int | None = Field(
        None,
        ge=1,
        le=5,
    )


@app.post("/chat/end")
async def end_chat(
    payload: EndChatRequest,
    origin: str = Header(None),
    db: AsyncSession = Depends(get_db),
):

    # --------------------------------------------------------
    # A. VERIFY TENANT
    # --------------------------------------------------------

    tenant_row = await db.execute(
        text(
            """
            SELECT website_domain
            FROM tenants
            WHERE tenant_id =
                CAST(:tid AS uuid)
            """
        ),
        {
            "tid": payload.tenant_id
        },
    )

    tenant = tenant_row.fetchone()

    if (
        not tenant
        or not tenant.website_domain
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Tenant not configured "
                "for widget access"
            ),
        )

    # --------------------------------------------------------
    # B. VERIFY ORIGIN
    # --------------------------------------------------------

    if (
        not origin
        or extract_origin(
            tenant.website_domain
        ) != origin
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Origin not authorized "
                "for this tenant"
            ),
        )

    # --------------------------------------------------------
    # C. VERIFY SESSION
    # --------------------------------------------------------

    session_result = await db.execute(
        text(
            """
            SELECT session_id
            FROM chat_sessions
            WHERE session_id =
                CAST(:sid AS uuid)
            AND tenant_id =
                CAST(:tid AS uuid)
            """
        ),
        {
            "sid": payload.session_id,
            "tid": payload.tenant_id,
        },
    )

    if not session_result.fetchone():

        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    # --------------------------------------------------------
    # D. END SESSION
    # --------------------------------------------------------

    await db.execute(
        text(
            """
            UPDATE chat_sessions
            SET
                status = 'completed',
                customer_satisfaction =
                    COALESCE(
                        :csat,
                        customer_satisfaction
                    ),
                end_datetime = NOW()
            WHERE session_id =
                CAST(:sid AS uuid)
            AND tenant_id =
                CAST(:tid AS uuid)
            """
        ),
        {
            "sid": payload.session_id,
            "tid": payload.tenant_id,
            "csat": payload.csat,
        },
    )

    await db.commit()

    return {
        "status": "success",
        "message": "Chat session ended",
    }



class WebsiteDomainUpdate(BaseModel):
    website_domain: str


@app.put("/tenants/website-domain")
async def update_website_domain(
    payload: WebsiteDomainUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text("""
            UPDATE tenants
            SET website_domain = :website_domain
            WHERE tenant_id = :tenant_id
            RETURNING tenant_id, website_domain
        """),
        {
            "website_domain": payload.website_domain,
            "tenant_id": current_user["tenant_id"],  # server-derived, not client-supplied
        },
    )
    await db.commit()
    row = result.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return dict(row._mapping)


class InviteAccept(BaseModel):
    invite_token: str
    user_id: str
    email: str


@app.post("/invite/accept")
async def accept_invite(
    payload: InviteAccept,
    verified_user_id: str = Depends(decode_jwt),
    db: AsyncSession = Depends(get_db),
):
    if payload.user_id != verified_user_id:
        raise HTTPException(status_code=403, detail="user_id does not match authenticated user")

    tenant_result = await db.execute(
        text("SELECT tenant_id FROM tenants WHERE invite_token = :token"),
        {"token": payload.invite_token},
    )
    tenant_row = tenant_result.fetchone()
    if not tenant_row:
        raise HTTPException(status_code=404, detail="Invalid invite link")

    existing = await db.execute(
        text("SELECT user_id FROM users WHERE user_id = :uid"), {"uid": payload.user_id}
    )
    if existing.fetchone():
        raise HTTPException(status_code=409, detail="User already registered")

    await db.execute(
        text("""
            INSERT INTO users (user_id, tenant_id, email, password_hash, role, status, invited_at)
            VALUES (:user_id, :tenant_id, :email, :password_hash, 'member', 'pending', now())
        """),
        {
            "user_id": payload.user_id,
            "tenant_id": tenant_row.tenant_id,
            "email": payload.email,
            "password_hash": "MANAGED_BY_SUPABASE_AUTH",
        },
    )
    await db.commit()
    return {"status": "pending", "tenant_id": str(tenant_row.tenant_id)}


class UserActionRequest(BaseModel):
    user_id: str


@app.get("/admin/pending-users")
async def get_pending_users(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user["role"] != "owner":
        raise HTTPException(status_code=403, detail="Owner access required")

    result = await db.execute(
        text("""
            SELECT user_id, email, invited_at, created_at
            FROM users
            WHERE tenant_id = :tenant_id AND status = 'pending'
            ORDER BY created_at ASC
        """),
        {"tenant_id": current_user["tenant_id"]},
    )
    rows = result.fetchall()
    return [dict(row._mapping) for row in rows]


@app.post("/admin/approve-user")
async def approve_user(
    payload: UserActionRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user["role"] != "owner":
        raise HTTPException(status_code=403, detail="Owner access required")

    result = await db.execute(
        text("""
            UPDATE users
            SET status = 'active', accepted_at = now()
            WHERE user_id = :user_id AND tenant_id = :tenant_id AND status = 'pending'
            RETURNING user_id, email, status
        """),
        {"user_id": payload.user_id, "tenant_id": current_user["tenant_id"]},
    )
    row = result.fetchone()
    await db.commit()

    if row is None:
        raise HTTPException(status_code=404, detail="No matching pending user found for your tenant")

    return dict(row._mapping)


@app.post("/admin/decline-user")
async def decline_user(
    payload: UserActionRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user["role"] != "owner":
        raise HTTPException(status_code=403, detail="Owner access required")

    result = await db.execute(
        text("""
            UPDATE users
            SET status = 'declined'
            WHERE user_id = :user_id AND tenant_id = :tenant_id AND status = 'pending'
            RETURNING user_id, email, status
        """),
        {"user_id": payload.user_id, "tenant_id": current_user["tenant_id"]},
    )
    row = result.fetchone()
    await db.commit()

    if row is None:
        raise HTTPException(status_code=404, detail="No matching pending user found for your tenant")

    return dict(row._mapping)


@app.get("/sessions")
async def list_sessions(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    min_csat: int | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Status is derived purely from end_datetime: NULL means the visitor never
    # clicked "End Chat" (still Ongoing), non-NULL means /chat/end ran (Completed).
    # No last-message-activity heuristic — that was a stopgap from before
    # /chat/end reliably wrote a real end_datetime, and is no longer needed.
    base_where = "WHERE cs.tenant_id = CAST(:tenant_id AS uuid)"
    params = {"tenant_id": current_user["tenant_id"]}

    if start_date:
        base_where += " AND cs.start_datetime >= :start_date::timestamp"
        params["start_date"] = start_date
    if end_date:
        base_where += " AND cs.start_datetime <= :end_date::timestamp"
        params["end_date"] = end_date
    if min_csat:
        base_where += " AND cs.customer_satisfaction >= :min_csat"
        params["min_csat"] = min_csat

    query_str = f"""
        SELECT
            cs.session_id,
            cs.start_datetime,
            cs.end_datetime,
            cs.customer_satisfaction,
            COUNT(m.message_id) AS message_count,
            CASE WHEN cs.end_datetime IS NULL THEN 'Ongoing' ELSE 'Completed' END AS status
        FROM chat_sessions cs
        LEFT JOIN messages m ON m.session_id = cs.session_id
        {base_where}
        GROUP BY cs.session_id
        ORDER BY cs.start_datetime DESC
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = limit
    params["offset"] = offset

    result = await db.execute(text(query_str), params)
    rows = result.fetchall()

    count_query_str = f"""
        SELECT COUNT(DISTINCT cs.session_id)
        FROM chat_sessions cs
        {base_where}
    """
    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
    total_result = await db.execute(text(count_query_str), count_params)
    total = total_result.scalar()

    return {
        "sessions": [dict(row._mapping) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify session ownership using CAST for UUID safety
    session_check = await db.execute(
        text("SELECT tenant_id FROM chat_sessions WHERE session_id = CAST(:session_id AS uuid)"),
        {"session_id": session_id},
    )
    session_row = session_check.fetchone()
    if session_row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if str(session_row.tenant_id) != current_user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Session does not belong to your tenant")

    messages_result = await db.execute(
        text("""
            SELECT message_id, sender, content, sentiment, response_latency_ms, created_at
            FROM messages
            WHERE session_id = CAST(:session_id AS uuid)
            ORDER BY created_at ASC
        """),
        {"session_id": session_id},
    )
    messages = [dict(row._mapping) for row in messages_result.fetchall()]

    if not messages:
        return []

    message_ids = [m["message_id"] for m in messages]

    sources_result = await db.execute(
        text("""
            SELECT ms.message_id, dc.chunk_text, dc.chunk_index, ms.relevance_score
            FROM message_sources ms
            JOIN document_chunks dc ON dc.chunk_id = ms.chunk_id
            WHERE ms.message_id = ANY(:message_ids)
            ORDER BY ms.relevance_score DESC
        """),
        {"message_ids": message_ids},
    )
    sources_by_message: dict = {}
    for row in sources_result.fetchall():
        sources_by_message.setdefault(str(row.message_id), []).append({
            "chunk_text": row.chunk_text,
            "chunk_index": row.chunk_index,
            "relevance_score": row.relevance_score,
        })

    for m in messages:
        m["sources"] = sources_by_message.get(str(m["message_id"]), [])

    return messages

@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    return {"status": "ok"}
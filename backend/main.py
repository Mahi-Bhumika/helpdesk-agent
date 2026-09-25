import asyncio
import os as os_module
import tempfile
from urllib.parse import urlparse

import time

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
from typing import Optional, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth import decode_jwt, get_current_user
from chunking import chunk_text, embed_chunks
from database import get_db
from extract_text import extract_text
from rate_limit import enforce_chat_rate_limit

import asyncio

from auth import get_current_user, decode_jwt

from fastapi import FastAPI, HTTPException, Depends, Header, Query

import re
import difflib

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


# --- Regex Compiled Patterns ---

_GREETING_PATTERN = re.compile(
    r"^\s*(h+[i|e|y]+|hello+|hey+|heya+|howdy+|hola+|good\s*(morning|afternoon|evening)|yo+|sup)\b",
    re.IGNORECASE
)

_ACKNOWLEDGMENT_PATTERN = re.compile(
    r"^\s*(thanks?|thank\s*you+|thx|ty|tysm|ok(ay)?|okie|got\s*it|cool|great|perfect|alright|sounds\s*good|awesome|nice|sure|no\s*problem|np)\b",
    re.IGNORECASE
)

_IDENTITY_STATUS_PATTERN = re.compile(
    r"^\s*(who\s*are\s*you|what\s*are\s*you|are\s*you\s*a\s*bot|how\s*are\s*you|what\s*is\s*your\s*name)\b",
    re.IGNORECASE
)

_ENUMERATION_PATTERNS = re.compile(
    r"\b("
    # "list all" / "list of all" / "a list of everything" — the old pattern
    # required "list" and "all" adjacent, so "a list of all you have" (a very
    # common real phrasing) never matched. (of\s+)? makes the "of" optional.
    r"list\s+(of\s+)?(all|everything)|full\s+list|complete\s+list|"
    r"all\s+(of\s+)?(the\s+|your\s+)?(products|services|items|things)|"
    r"what\s+(services|products|items)\s+do\s+you\s+(offer|have|sell)|"
    r"everything\s+you\s+(offer|have|sell)|catalog|"
    r"show\s+(me\s+)?(all|everything)|"
    r"what\s+do\s+you\s+(offer|sell|have)|"
    r"what\s+all\s+(do\s+you\s+)?(have|offer|sell)"
    r")\b",
    re.IGNORECASE
)

_SUMMARY_PATTERNS = re.compile(
    r"\b("
    r"summarize|summary|give\s+me\s+a\s+summary|brief\s+overview|recap|tl;?dr"
    r")\b",
    re.IGNORECASE
)

_FOLLOWUP_TRIGGERS = [
    "tell me more", "more details", "how much", "price", "cost",
    "and the other", "what about", "the other one", "both", "this",
    "that", "these", "it", "how much is it", "why", "where",
    "can i get", "is it available", "how do i", "any other", "other options",
    "what else", "and?", "and", "anything else", "more", "others"
]

# --- Typo-tolerant smalltalk word lists (fuzzy fallback below) ---
_GREETING_WORDS = [
    "hi", "hii", "hiii", "hey", "heyy", "heya", "hello", "helloo",
    "howdy", "hola", "yo", "yoo", "sup", "gm", "gmorning",
]
_GREETING_PHRASES = ["good morning", "good afternoon", "good evening"]
_ACK_WORDS = [
    "thanks", "thankyou", "thank you", "thx", "ty", "tysm", "ok", "okay",
    "okie", "got it", "cool", "great", "perfect", "alright", "sounds good",
    "awesome", "nice", "sure", "no problem", "np",
]
_IDENTITY_PHRASES = [
    "who are you", "what are you", "are you a bot", "how are you",
    "what is your name",
]


# --- Classification & Intent Helpers ---

def _fuzzy_match(token: str, candidates: list[str], cutoff: float = 0.72) -> bool:
    """
    True if `token` is an exact or close (typo-tolerant) match to any
    candidate phrase, using edit-distance-style similarity rather than a
    fixed regex, so misspellings like 'heoll' or 'gmm' still resolve to
    their intended word.
    """
    if not token:
        return False
    if token in candidates:
        return True
    return bool(difflib.get_close_matches(token, candidates, n=1, cutoff=cutoff))


def classify_smalltalk(question: str, has_history: bool = False) -> Optional[tuple[str, str]]:
    """
    Classifies standalone smalltalk (greetings, acknowledgments, identity questions).
    Bypasses smalltalk if the message contains > 5 words to prevent capturing contextual queries.

    Runs the exact regexes first (cheap, precise), then — only for very short
    inputs (<=3 words), to avoid misclassifying real questions — falls back to
    fuzzy/typo-tolerant matching against known phrase lists. This is what
    catches variants the regex can't enumerate, like 'heoll', 'gmm', or 'tanx'.
    """
    raw_cleaned = question.strip()
    word_count = len(raw_cleaned.split())

    if word_count > 5:
        return None

    if _IDENTITY_STATUS_PATTERN.search(raw_cleaned):
        return ("identity", "I am an AI support assistant here to help answer your questions based on our knowledge base.")

    if _GREETING_PATTERN.search(raw_cleaned):
        return ("greeting", "greeting_placeholder")

    if _ACKNOWLEDGMENT_PATTERN.search(raw_cleaned):
        return ("acknowledgment", "You're welcome! Let me know if there's anything else I can help with.")

    if word_count <= 3:
        normalized = re.sub(r"[^a-z\s]", "", raw_cleaned.lower()).strip()
        normalized = re.sub(r"\s+", " ", normalized)
        first_word = normalized.split()[0] if normalized else ""

        if not normalized:
            return None

        if _fuzzy_match(normalized, _IDENTITY_PHRASES, cutoff=0.8):
            return ("identity", "I am an AI support assistant here to help answer your questions based on our knowledge base.")

        if _fuzzy_match(first_word, _GREETING_WORDS, cutoff=0.72) or _fuzzy_match(normalized, _GREETING_PHRASES, cutoff=0.72):
            return ("greeting", "greeting_placeholder")

        if _fuzzy_match(normalized, _ACK_WORDS, cutoff=0.75) or _fuzzy_match(first_word, _ACK_WORDS, cutoff=0.75):
            return ("acknowledgment", "You're welcome! Let me know if there's anything else I can help with.")

    return None

def is_enumeration_query(question: str) -> bool:
    """Detects exhaustive catalog listing requests."""
    return bool(_ENUMERATION_PATTERNS.search(question))

def is_summary_query(question: str) -> bool:
    """Detects requests asking for a summary/overview."""
    return bool(_SUMMARY_PATTERNS.search(question))


# Short "is there more?" follow-ups. Distinct from _FOLLOWUP_TRIGGERS (which
# just decides whether to rewrite the query) — these specifically mean "have
# you told me everything," which needs a different reply than the generic
# fallback when the honest answer is "yes, that's the full list."
_CONTINUATION_TRIGGERS = [
    "and?", "anything else", "any other", "any others", "others",
    "other options", "what else", "more options", "any more",
    "is that all", "is that it", "thats it", "that's it",
    "what about the rest", "more",
]


def is_continuation_query(question: str) -> bool:
    """Detects a short 'anything else / is that all?' style follow-up."""
    q = question.strip().lower().rstrip("?!.")
    if not q or len(q.split()) > 6:
        return False
    return q == "and" or any(t.rstrip("?!.") in q for t in _CONTINUATION_TRIGGERS)


# --- Query Reformulation Logic ---

def _needs_query_rewrite(question: str, history_rows: list) -> bool:
    """
    Triggers query rewriting if there is conversation history AND either:
    1. The question is short (<= 6 words).
    2. The question contains implicit context triggers ('and?', 'what about', 'how much').
    """
    if not history_rows:
        return False

    q_lower = question.strip().lower()

    if len(q_lower.split()) <= 6:
        return True

    return any(trigger in q_lower for trigger in _FOLLOWUP_TRIGGERS)

def _rewrite_query_for_retrieval(question: str, history_rows: list) -> str:
    """Rephrases follow-up questions into standalone search queries using Groq."""
    history_str = "\n".join([
        f"{'User' if getattr(h, 'sender', '') == 'user' else 'Assistant'}: {getattr(h, 'content', '')}"
        for h in history_rows[-4:]
    ])

    rewrite_prompt = [
        {
            "role": "system",
            "content": (
                "You are a search query reformulation module. Given a conversation history and a follow-up user message, "
                "rephrase the follow-up message into a complete, standalone search query containing all necessary entity "
                "names, products, and specifics from history. Preserve the user's original intent — if they are asking "
                "for a list, a summary/overview, or a price, keep that instruction explicit in the rewritten query "
                "(e.g. 'pricing for the Pro plan', 'summary of the Starter plan features'). "
                "Output ONLY the rephrased search query, nothing else."
            ),
        },
        {
            "role": "user",
            "content": f"Conversation History:\n{history_str}\n\nFollow-up User Message: {question}\n\nStandalone Search Query:",
        },
    ]

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=rewrite_prompt,
            temperature=0.0,
            max_tokens=60,
        )
        rewritten = response.choices[0].message.content.strip().strip('"')
        return rewritten if rewritten else question
    except Exception as e:  # noqa: BLE001 — any rewrite failure should fall back to the raw question
        print(f"[DEBUG] Query rewrite failed: {e}")
    return question


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
 
# Similarity threshold for retrieval — confirmed at 0.35. Chunks scoring below
# this (1 - cosine_distance) are treated as not relevant enough to answer from.
SIMILARITY_THRESHOLD = 0.35
 
# Separate, looser settings for detected "list everything" queries — the goal
# there is coverage, not precision, so cast a much wider net: more chunks,
# and a much lower bar for "relevant enough to include." Still bounded, not
# unlimited — 25 chunks is generous for this project's real chunk counts
# (a few dozen per document) without risking an oversized LLM prompt.
ENUMERATION_TOP_K = 25
ENUMERATION_SIMILARITY_THRESHOLD = 0.15

# How far below SIMILARITY_THRESHOLD a single best match is still allowed to
# fall before we give up entirely on an ordinary (non-enum/summary) query.
# This exists purely to stop the hard 0.35 cliff from turning a genuinely
# relevant top hit (e.g. 0.30 similarity) into a false "no context" fallback.
RELAXED_RETRY_FLOOR = 0.20
 

# --- Primary Endpoint ---

@app.post("/chat", response_model=ChatResponse)
async def chat(query: ChatQuery, origin: str = Header(None), db: AsyncSession = Depends(get_db)):
    enforce_chat_rate_limit(query.tenant_id)
    top_k = min(query.top_k, 10)

    # 1. Fetch Tenant Configuration
    tenant_row = await db.execute(
        text("SELECT website_domain, fallback_message, bot_name, greeting_message FROM tenants WHERE tenant_id = CAST(:tid AS uuid)"),
        {"tid": query.tenant_id},
    )
    tenant = tenant_row.fetchone()
    if not tenant or not tenant.website_domain:
        raise HTTPException(status_code=403, detail="Tenant not configured for widget access")
    if not origin or extract_origin(tenant.website_domain) != origin:
        raise HTTPException(status_code=403, detail="Origin not authorized for this tenant")

    # 2. Session Initialization / Verification
    session_id = query.session_id
    if session_id:
        existing_session = await db.execute(
            text("SELECT session_id FROM chat_sessions WHERE session_id = CAST(:sid AS uuid) AND tenant_id = CAST(:tid AS uuid)"),
            {"sid": session_id, "tid": query.tenant_id}
        )
        if not existing_session.fetchone():
            session_id = None

    if not session_id:
        session_result = await db.execute(
            text("""
                INSERT INTO chat_sessions (tenant_id)
                VALUES (CAST(:tenant_id AS uuid))
                RETURNING session_id
            """),
            {"tenant_id": query.tenant_id},
        )
        session_id = str(session_result.fetchone().session_id)

    # 3. Fetch Active Conversation History (Last 6 Turns)
    history_result = await db.execute(
        text("""
            SELECT sender, content 
            FROM messages 
            WHERE session_id = CAST(:session_id AS uuid) 
            ORDER BY created_at DESC 
            LIMIT 6
        """),
        {"session_id": session_id}
    )
    history_rows = list(reversed(history_result.fetchall()))

    # 4. Context-Aware Smalltalk Fast-Path
    smalltalk_match = classify_smalltalk(query.question, has_history=bool(history_rows))
    if smalltalk_match:
        kind, canned_reply = smalltalk_match
        if kind == "greeting":
            reply = tenant.greeting_message or "Hello! How can I help you today?"
        else:
            reply = canned_reply

        # Persist conversation turn
        await db.execute(
            text("INSERT INTO messages (session_id, tenant_id, sender, content) VALUES (CAST(:session_id AS uuid), CAST(:tenant_id AS uuid), 'user', :content)"),
            {"session_id": session_id, "tenant_id": query.tenant_id, "content": query.question},
        )
        await db.execute(
            text("INSERT INTO messages (session_id, tenant_id, sender, content) VALUES (CAST(:session_id AS uuid), CAST(:tenant_id AS uuid), 'bot', :content)"),
            {"session_id": session_id, "tenant_id": query.tenant_id, "content": reply},
        )
        await db.commit()
        return ChatResponse(session_id=str(session_id), answer=reply, sources=[])

    # 5. Query Classification & Vector Retrieval Config
    is_enum = is_enumeration_query(query.question)
    is_summary = is_summary_query(query.question)
    is_continuation = is_continuation_query(query.question)

    retrieval_query_text = query.question

    # Rewrite runs for ANY short/contextual follow-up, including enumeration
    # and summary requests — is_enum/is_summary are already computed above
    # from the ORIGINAL question, so effective_top_k / effective_threshold
    # below are unaffected either way. Previously this was skipped for
    # is_enum/is_summary, which meant a follow-up like "summarize that" or
    # "list pricing for it" never had its pronoun resolved before embedding,
    # so it had nothing meaningful to match against and fell through to the
    # fallback message.
    if _needs_query_rewrite(query.question, history_rows):
        retrieval_query_text = _rewrite_query_for_retrieval(query.question, history_rows)
        print(f"[DEBUG] Rewritten query for vector search: '{retrieval_query_text}'")

    query_embedding = embed_chunks([retrieval_query_text])[0]
    
    # Expand retrieval scope for enumeration, summary, or "is there more?"
    # queries — the last one needs the wide net too, since we can only tell
    # someone "that's everything" in good faith if we actually looked broadly.
    _wide_scope = is_enum or is_summary or is_continuation
    effective_top_k = ENUMERATION_TOP_K if _wide_scope else top_k
    effective_threshold = ENUMERATION_SIMILARITY_THRESHOLD if _wide_scope else SIMILARITY_THRESHOLD

    # 6. Database Vector Search
    search_query = text("""
        SELECT chunk_id, chunk_text, chunk_index, document_id, embedding <=> :query_embedding AS distance
        FROM document_chunks
        WHERE tenant_id = CAST(:tenant_id AS uuid)
        ORDER BY embedding <=> :query_embedding
        LIMIT :top_k
    """)
    result = await db.execute(search_query, {
        "query_embedding": str(query_embedding),
        "tenant_id": query.tenant_id,
        "top_k": effective_top_k,
    })
    rows = result.fetchall()

    # 7. Threshold Filtering
    retrieved_chunks = [
        dict(row._mapping) for row in rows
        if (1 - row.distance) >= effective_threshold
    ]

    # Safety-net retry: a hard similarity cliff can wrongly discard a
    # genuinely relevant single best match (e.g. 0.30 vs a 0.35 bar) for an
    # ordinary question, producing a false fallback even though the answer
    # is right there. If nothing cleared the bar, accept the single best
    # match as long as it's still reasonably close (>= RELAXED_RETRY_FLOOR).
    # Enumeration/summary queries already use a wide net, so they're excluded.
    if not retrieved_chunks and rows and not _wide_scope:
        best = rows[0]
        if (1 - best.distance) >= RELAXED_RETRY_FLOOR:
            retrieved_chunks = [dict(best._mapping)]
            print(f"[DEBUG] Relaxed-threshold retry accepted best match at similarity {1 - best.distance:.3f}")

    context = "\n\n---\n\n".join(chunk["chunk_text"] for chunk in retrieved_chunks) if retrieved_chunks else "NO_RELEVANT_CONTEXT_FOUND"
    fallback_text = tenant.fallback_message or "Sorry, I don't have an answer for that — try rephrasing or contact support."

    # 7b. "Anything else?" resolution: if this is a continuation query, check
    # whether the chunks it just retrieved are all chunks that were already
    # cited earlier in this session. If so, the honest answer isn't "I don't
    # understand" — it's "that's everything." We only make this call when
    # something was genuinely already discussed (already_cited_ids non-empty);
    # otherwise this falls through to the normal path below.
    no_more_items = False
    if is_continuation and history_rows:
        prior_sources_result = await db.execute(
            text("""
                SELECT DISTINCT ms.chunk_id
                FROM message_sources ms
                JOIN messages m ON m.message_id = ms.message_id
                WHERE m.session_id = CAST(:session_id AS uuid)
            """),
            {"session_id": session_id},
        )
        already_cited_ids = {str(r.chunk_id) for r in prior_sources_result.fetchall()}
        new_chunk_ids = {str(c["chunk_id"]) for c in retrieved_chunks} - already_cited_ids
        no_more_items = bool(already_cited_ids) and not new_chunk_ids

    # 8. Construct Prompt Instructions
    if no_more_items:
        # Dedicated prompt for this branch: confirm, don't apologize. The
        # STRICT CONTEXT RULE prompt below would otherwise have no way to
        # distinguish "off-topic" from "you've now heard the full list," and
        # would output the generic fallback for both.
        system_prompt = (
            f"You are {tenant.bot_name or 'a helpful AI assistant'}, a support assistant for this business.\n"
            "The user is asking if there's anything else / any other options, as a follow-up to what you already "
            "told them earlier in this conversation. The Retrieved Context below contains nothing beyond what was "
            "already discussed — meaning what you already mentioned is the complete offering in that category.\n"
            "Reply in one short, warm sentence confirming that's everything currently available in that category. "
            "Do NOT say you don't understand, do NOT ask them to rephrase, and do NOT invent any new items."
        )
    else:
        system_prompt = (
            f"You are {tenant.bot_name or 'a helpful AI assistant'}, a support assistant for this business.\n"
            "Use plain, clear, conversational language without headers. Default to 2-4 short sentences.\n\n"
            "Formatting Exceptions:\n"
            "1. Step-by-step requests: Use a short, clear numbered list.\n"
            "2. List/Catalog/Summary requests: Compile a clear, comprehensive bullet-point list using all relevant facts in the 'Retrieved Context'.\n"
            "3. Mid-conversation acknowledgments (e.g., 'thanks', 'got it'): Respond warmly in 1 short sentence without triggering fallback.\n\n"
            "STRICT CONTEXT RULE: You may ONLY answer using factual information explicitly found in the 'Retrieved Context' below. "
            "Do not invent facts, assume details, or draw on external knowledge.\n\n"
            "If the requested information is NOT present in the Retrieved Context, output strictly and exactly this message and nothing else:\n"
            f'"{fallback_text}"\n\n'
            "Use conversation history only to understand follow-up references (e.g., 'it', 'that price', 'tell me more') — never as an independent source of unverified facts."
        )

    llm_messages = [{"role": "system", "content": system_prompt}]
    for h in history_rows:
        role = "user" if h.sender == "user" else "assistant"
        llm_messages.append({"role": role, "content": h.content})

    user_prompt = f"Retrieved Context:\n{context}\n\nUser Question: {query.question}"
    llm_messages.append({"role": "user", "content": user_prompt})

    # 9. LLM Answer Generation
    completion = groq_client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=llm_messages,
    )
    answer = completion.choices[0].message.content

    # 10. Persist Dialogue Turn to DB
    await db.execute(
        text("INSERT INTO messages (session_id, tenant_id, sender, content) VALUES (CAST(:session_id AS uuid), CAST(:tenant_id AS uuid), 'user', :content)"),
        {"session_id": session_id, "tenant_id": query.tenant_id, "content": query.question},
    )

    bot_message_result = await db.execute(
        text("INSERT INTO messages (session_id, tenant_id, sender, content) VALUES (CAST(:session_id AS uuid), CAST(:tenant_id AS uuid), 'bot', :content) RETURNING message_id"),
        {"session_id": session_id, "tenant_id": query.tenant_id, "content": answer},
    )
    bot_message_id = bot_message_result.fetchone().message_id

    # 11. Store Citations & Commit
    sources = []
    # Store citations only if context was found, fallback wasn't triggered,
    # and this isn't the "no_more_items" branch (those chunks were already
    # cited against an earlier message in this session — no need to duplicate).
    if retrieved_chunks and answer.strip() != fallback_text.strip() and not no_more_items:
        source_rows = [
            {
                "message_id": bot_message_id,
                "chunk_id": chunk["chunk_id"],
                "relevance_score": 1 - chunk["distance"],
            }
            for chunk in retrieved_chunks
        ]
        await db.execute(
            text("""
                INSERT INTO message_sources (message_id, chunk_id, relevance_score)
                VALUES (:message_id, :chunk_id, :relevance_score)
            """),
            source_rows,
        )
        sources = [
            ChatSource(chunk_id=str(r["chunk_id"]), relevance_score=r["relevance_score"])
            for r in source_rows
        ]

    await db.commit()

    return ChatResponse(session_id=str(session_id), answer=answer, sources=sources)

class EndChatRequest(BaseModel):
    session_id: str
    tenant_id: str
    csat: int | None = Field(None, ge=1, le=5)


@app.post("/chat/end")
async def end_chat(
    payload: EndChatRequest,
    origin: str = Header(None),
    db: AsyncSession = Depends(get_db),
):
    # Same Origin check as /chat — ending/rating a session is still an action
    # tied to a specific tenant's own widget, not something an arbitrary script
    # with a guessed session_id should be able to trigger.
    tenant_row = await db.execute(
        text("SELECT website_domain FROM tenants WHERE tenant_id = CAST(:tid AS uuid)"),
        {"tid": payload.tenant_id},
    )
    tenant = tenant_row.fetchone()
    if not tenant or not tenant.website_domain:
        raise HTTPException(status_code=403, detail="Tenant not configured for widget access")
    if not origin or extract_origin(tenant.website_domain) != origin:
        raise HTTPException(status_code=403, detail="Origin not authorized for this tenant")

    # Verify session exists and belongs to this tenant
    session_result = await db.execute(
        text("""
            SELECT session_id 
            FROM chat_sessions 
            WHERE session_id = CAST(:sid AS uuid) AND tenant_id = CAST(:tid AS uuid)
        """),
        {"sid": payload.session_id, "tid": payload.tenant_id},
    )
    if not session_result.fetchone():
        raise HTTPException(status_code=404, detail="Session not found")

    # Update status, save csat, and set ending timestamp.
    # end_datetime is only ever written here — a session's status is derived
    # solely from whether this has run (i.e. the visitor clicked "End Chat"),
    # never from a last-activity heuristic.
    await db.execute(
        text("""
            UPDATE chat_sessions
            SET status = 'completed',
                customer_satisfaction = COALESCE(:csat, customer_satisfaction),
                end_datetime = NOW()
            WHERE session_id = CAST(:sid AS uuid) AND tenant_id = CAST(:tid AS uuid)
        """),
        {
            "sid": payload.session_id,
            "tid": payload.tenant_id,
            "csat": payload.csat,
        },
    )
    await db.commit()

    return {"status": "success", "message": "Chat session ended"}


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

@app.get("/health")
def health():
    return {"status": "ok"}
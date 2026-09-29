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
# SMALLTALK PATTERNS
# ============================================================

_GREETING_PATTERN = re.compile(
    r"^\s*(h+[i|e|y]+|hello+|hey+|heya+|howdy+|hola+|"
    r"good\s*(morning|afternoon|evening)|yo+|sup)\b",
    re.IGNORECASE,
)

_ACKNOWLEDGMENT_PATTERN = re.compile(
    r"^\s*(thanks?|thank\s*you+|thx|ty|tysm|ok(ay)?|okie|got\s*it|"
    r"cool|great|perfect|alright|sounds\s*good|awesome|nice|sure|"
    r"no\s*problem|np)\b",
    re.IGNORECASE,
)

_IDENTITY_STATUS_PATTERN = re.compile(
    r"^\s*(who\s*are\s*you|what\s*are\s*you|are\s*you\s*a\s*bot|"
    r"how\s*are\s*you|what\s*is\s*your\s*name)\b",
    re.IGNORECASE,
)


_GREETING_WORDS = [
    "hi",
    "hii",
    "hiii",
    "hey",
    "heyy",
    "heya",
    "hello",
    "helloo",
    "howdy",
    "hola",
    "yo",
    "yoo",
    "sup",
    "gm",
    "gmorning",
]

_GREETING_PHRASES = [
    "good morning",
    "good afternoon",
    "good evening",
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
    """
    Detects standalone smalltalk.

    Important:
    Long questions are never treated as smalltalk.
    """

    raw_cleaned = question.strip()
    word_count = len(raw_cleaned.split())

    if word_count > 5:
        return None

    if _IDENTITY_STATUS_PATTERN.search(raw_cleaned):
        return (
            "identity",
            "I am an AI support assistant here to help answer your questions based on our knowledge base.",
        )

    if _GREETING_PATTERN.search(raw_cleaned):
        return ("greeting", "greeting_placeholder")

    if _ACKNOWLEDGMENT_PATTERN.search(raw_cleaned):
        return (
            "acknowledgment",
            "You're welcome! Let me know if there's anything else I can help with.",
        )

    if word_count <= 3:

        normalized = re.sub(
            r"[^a-z\s]",
            "",
            raw_cleaned.lower(),
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
                "I am an AI support assistant here to help answer your questions based on our knowledge base.",
            )

        if (
            _fuzzy_match(
                first_word,
                _GREETING_WORDS,
                cutoff=0.72,
            )
            or _fuzzy_match(
                normalized,
                _GREETING_PHRASES,
                cutoff=0.72,
            )
        ):
            return ("greeting", "greeting_placeholder")

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
# QUERY INTENT
# ============================================================

class QueryIntent(str, Enum):
    factual = "factual"
    attribute_lookup = "attribute_lookup"
    multi_entity_attribute = "multi_entity_attribute"
    comparison = "comparison"
    summary = "summary"
    catalog = "catalog"
    continuation = "continuation"
    clarification = "clarification"


class ResolvedQuery(BaseModel):
    standalone_query: str

    intent: QueryIntent

    entities: list[str] = Field(
        default_factory=list
    )

    attributes: list[str] = Field(
        default_factory=list
    )

    comparison_operator: str | None = None

    requires_all_products: bool = False

    requires_previous_context: bool = False


# ============================================================
# QUERY RESOLUTION
# ============================================================

def resolve_query(
    question: str,
    history_rows: list,
) -> ResolvedQuery:
    """
    Converts a conversational question into a standalone
    retrieval query.

    Example:

        User:
        "which product has the maximum coverage?"

        User:
        "what's the price of it?"

    becomes approximately:

        "What is the price of the AetherVane Pro-X?"
    """

    history_text = "\n".join(
        [
            (
                f"{'User' if getattr(h, 'sender', '') == 'user' else 'Assistant'}: "
                f"{getattr(h, 'content', '')}"
            )
            for h in history_rows[-8:]
        ]
    )

    resolver_prompt = """
You are the query-resolution layer of a RAG customer-support system.

DO NOT answer the user's question.

Your job is to understand the current user message using
the conversation history and produce a structured query
for document retrieval.

IMPORTANT RULES:

1. Resolve conversational references.

Examples:

"what's its price?"
"what is the price of it?"
"what about that one?"
"tell me more about it"
"what are their prices?"
"is it the biggest?"
"what about the other one?"

Resolve "it", "its", "that", "this", "they", "their",
"these", "those", and similar references using conversation
history.

2. Preserve exact product/entity names whenever they are
available in the conversation.

3. NEVER invent a product or entity.

4. If the user asks about ALL products, set:

requires_all_products = true

5. Comparison questions include:

- most expensive
- cheapest
- largest
- smallest
- maximum
- minimum
- highest
- lowest
- biggest
- best
- worst

6. For comparison questions, identify the attribute.

Examples:

"most expensive"
→ attribute: price
→ comparison_operator: maximum

"cheapest"
→ attribute: price
→ comparison_operator: minimum

"maximum area coverage"
→ attribute: area coverage
→ comparison_operator: maximum

"lowest power"
→ attribute: power
→ comparison_operator: minimum

7. DO NOT invent what "best" means.

If the user says "is it the best product?",
retrieve information about that product and the available
product attributes, but do not decide that "best" means
price, coverage, power, etc. unless the conversation
explicitly establishes that.

8. Summary questions should identify the entity being
summarized.

Examples:

"summarize it"
→ summary of the previously discussed product

"give me a summary of the products"
→ catalog/summary across products

9. If the question asks for a property of multiple products,
use:

intent = "multi_entity_attribute"

10. If the user asks for all products, services, offerings,
catalog items, etc., use:

intent = "catalog"

11. If the user asks whether there is anything else / more
options / other products, use:

intent = "continuation"

12. standalone_query must be a complete search query containing
all necessary entity names and requested attributes.

13. The standalone_query should be optimized for retrieval,
not conversational.

Return ONLY valid JSON matching the requested schema.
"""

    messages = [
        {
            "role": "system",
            "content": resolver_prompt,
        },
        {
            "role": "user",
            "content": (
                f"Conversation History:\n"
                f"{history_text or '(no previous conversation)'}\n\n"
                f"Current User Question:\n"
                f"{question}"
            ),
        },
    ]

    try:

        completion = groq_client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=messages,
            temperature=0,
            max_tokens=500,
            response_format={
                "type": "json_object",
            },
        )

        raw = completion.choices[0].message.content

        parsed = json.loads(raw)

        resolved = ResolvedQuery.model_validate(parsed)

        print(
            "[DEBUG] Query resolved:",
            resolved.model_dump(),
        )

        return resolved

    except Exception as e:  # noqa: BLE001

        print(
            f"[DEBUG] Query resolver failed: {e}"
        )

        # Safe fallback.
        return ResolvedQuery(
            standalone_query=question,
            intent=QueryIntent.factual,
        )


# ============================================================
# SIMPLE QUERY DETECTORS
# ============================================================

_ENUMERATION_PATTERNS = re.compile(
    r"\b("
    r"list\s+(of\s+)?(all|everything)|"
    r"full\s+list|"
    r"complete\s+list|"
    r"all\s+(of\s+)?(the\s+|your\s+)?"
    r"(products|services|items|things)|"
    r"what\s+(services|products|items)\s+do\s+you\s+"
    r"(offer|have|sell)|"
    r"everything\s+you\s+(offer|have|sell)|"
    r"catalog|"
    r"show\s+(me\s+)?(all|everything)|"
    r"what\s+do\s+you\s+(offer|sell|have)|"
    r"what\s+all\s+(do\s+you\s+)?(have|offer|sell)"
    r")\b",
    re.IGNORECASE,
)


_SUMMARY_PATTERNS = re.compile(
    r"\b("
    r"summarize|"
    r"summary|"
    r"give\s+me\s+a\s+summary|"
    r"brief\s+overview|"
    r"recap|"
    r"tl;?dr"
    r")\b",
    re.IGNORECASE,
)


_CONTINUATION_TRIGGERS = [
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


def is_enumeration_query(
    question: str,
) -> bool:
    return bool(
        _ENUMERATION_PATTERNS.search(question)
    )


def is_summary_query(
    question: str,
) -> bool:
    return bool(
        _SUMMARY_PATTERNS.search(question)
    )


def is_continuation_query(
    question: str,
) -> bool:

    q = (
        question
        .strip()
        .lower()
        .rstrip("?!.")
    )

    if not q:
        return False

    if len(q.split()) > 6:
        return False

    if q == "and":
        return True

    return any(
        trigger.rstrip("?!.") in q
        for trigger in _CONTINUATION_TRIGGERS
    )


# ============================================================
# API MODELS
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
# RETRIEVAL SETTINGS
# ============================================================

NORMAL_TOP_K = 8
ENTITY_TOP_K = 15
COMPARISON_TOP_K = 40
SUMMARY_TOP_K = 30
CATALOG_TOP_K = 40
CONTINUATION_TOP_K = 40

NORMAL_THRESHOLD = 0.25
ENTITY_THRESHOLD = 0.12
COMPARISON_THRESHOLD = 0.12
SUMMARY_THRESHOLD = 0.12
CATALOG_THRESHOLD = 0.12
CONTINUATION_THRESHOLD = 0.12

MAX_CONTEXT_CHARS = 24000


# ============================================================
# ENTITY-AWARE VECTOR RETRIEVAL
# ============================================================

async def retrieve_chunks(
    db: AsyncSession,
    tenant_id: str,
    query_embedding,
    resolved: ResolvedQuery,
):
    """
    Performs vector retrieval while giving exact entity mentions
    priority.

    This is important for follow-ups like:

        "what's the price of it?"

because pure vector similarity can otherwise return generic
price chunks instead of the price chunk belonging to the
previously discussed product.
    """

    intent = resolved.intent

    if resolved.requires_all_products:
        top_k = CATALOG_TOP_K
        threshold = CATALOG_THRESHOLD

    elif intent == QueryIntent.comparison:
        top_k = COMPARISON_TOP_K
        threshold = COMPARISON_THRESHOLD

    elif intent == QueryIntent.summary:
        top_k = SUMMARY_TOP_K
        threshold = SUMMARY_THRESHOLD

    elif intent == QueryIntent.catalog:
        top_k = CATALOG_TOP_K
        threshold = CATALOG_THRESHOLD

    elif intent == QueryIntent.continuation:
        top_k = CONTINUATION_TOP_K
        threshold = CONTINUATION_THRESHOLD

    elif resolved.entities:
        top_k = ENTITY_TOP_K
        threshold = ENTITY_THRESHOLD

    else:
        top_k = NORMAL_TOP_K
        threshold = NORMAL_THRESHOLD

    top_k = min(
        top_k,
        50,
    )

    # --------------------------------------------------------
    # Build entity matching conditions.
    #
    # We don't use these as the ONLY retrieval mechanism.
    # Vector similarity still matters.
    # --------------------------------------------------------

    entity_conditions = []
    entity_params = {}

    for i, entity in enumerate(
        resolved.entities[:8]
    ):

        param_name = f"entity_{i}"

        entity_conditions.append(
            f"LOWER(chunk_text) LIKE LOWER(:{param_name})"
        )

        entity_params[param_name] = (
            f"%{entity}%"
        )

    if entity_conditions:

        entity_match_sql = (
            " OR ".join(entity_conditions)
        )

    else:

        entity_match_sql = "FALSE"

    search_query = text(
        f"""
        SELECT
            chunk_id,
            chunk_text,
            chunk_index,
            document_id,

            embedding <=> :query_embedding AS distance,

            CASE
                WHEN {entity_match_sql}
                THEN 0
                ELSE 1
            END AS entity_match

        FROM document_chunks

        WHERE tenant_id = CAST(:tenant_id AS uuid)

        ORDER BY
            entity_match ASC,
            embedding <=> :query_embedding ASC

        LIMIT :top_k
        """
    )

    result = await db.execute(
        search_query,
        {
            "query_embedding": str(
                query_embedding
            ),
            "tenant_id": tenant_id,
            "top_k": top_k,
            **entity_params,
        },
    )

    rows = result.fetchall()

    retrieved_chunks = []

    for row in rows:

        similarity = (
            1 - float(row.distance)
        )

        # Exact entity matches get a more permissive
        # threshold because lexical entity matching gives
        # us strong evidence that the chunk is about the
        # requested product.
        if row.entity_match == 0:

            keep = similarity >= 0.05

        else:

            keep = similarity >= threshold

        if keep:

            chunk = dict(
                row._mapping
            )

            chunk["similarity"] = similarity

            retrieved_chunks.append(
                chunk
            )

    # --------------------------------------------------------
    # Deduplicate
    # --------------------------------------------------------

    seen = set()
    deduped = []

    for chunk in retrieved_chunks:

        chunk_id = str(
            chunk["chunk_id"]
        )

        if chunk_id in seen:
            continue

        seen.add(chunk_id)

        deduped.append(chunk)

    retrieved_chunks = deduped

    print(
        "[DEBUG] Retrieved chunks:",
        [
            {
                "chunk_id": str(
                    c["chunk_id"]
                ),
                "similarity": round(
                    c["similarity"],
                    3,
                ),
                "entity_match": c.get(
                    "entity_match"
                ),
            }
            for c in retrieved_chunks
        ],
    )

    return retrieved_chunks


# ============================================================
# CONTEXT BUILDER
# ============================================================

def build_context(
    retrieved_chunks: list[dict],
) -> str:

    if not retrieved_chunks:
        return "NO_RELEVANT_CONTEXT_FOUND"

    context_parts = []
    total_chars = 0

    for index, chunk in enumerate(
        retrieved_chunks
    ):

        block = (
            f"[Source {index + 1}]\n"
            f"{chunk['chunk_text']}"
        )

        if (
            total_chars
            + len(block)
            > MAX_CONTEXT_CHARS
        ):
            break

        context_parts.append(
            block
        )

        total_chars += len(block)

    if not context_parts:
        return "NO_RELEVANT_CONTEXT_FOUND"

    return "\n\n---\n\n".join(
        context_parts
    )


# ============================================================
# MAIN CHAT ENDPOINT
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

    # ========================================================
    # 1. TENANT CONFIGURATION
    # ========================================================

    tenant_row = await db.execute(
        text(
            """
            SELECT
                website_domain,
                fallback_message,
                bot_name,
                greeting_message
            FROM tenants
            WHERE tenant_id = CAST(:tid AS uuid)
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

    # ========================================================
    # 2. SESSION
    # ========================================================

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
            session_result
            .fetchone()
            .session_id
        )

    # ========================================================
    # 3. CONVERSATION HISTORY
    # ========================================================

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

    # ========================================================
    # 4. SMALLTALK
    # ========================================================

    smalltalk_match = classify_smalltalk(
        query.question,
        has_history=bool(
            history_rows
        ),
    )

    if smalltalk_match:

        kind, canned_reply = (
            smalltalk_match
        )

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
            session_id=str(
                session_id
            ),
            answer=reply,
            sources=[],
        )

    # ========================================================
    # 5. RESOLVE QUERY
    # ========================================================

    resolved = resolve_query(
        question=query.question,
        history_rows=history_rows,
    )

    # Explicit continuation override.
    if is_continuation_query(
        query.question
    ):

        resolved.intent = (
            QueryIntent.continuation
        )

        resolved.requires_all_products = True

    print(
        "[DEBUG] Final resolved query:",
        resolved.model_dump(),
    )

    # ========================================================
    # 6. EMBEDDING
    # ========================================================

    retrieval_query_text = (
        resolved.standalone_query
    )

    query_embedding = embed_chunks(
        [retrieval_query_text]
    )[0]

    # ========================================================
    # 7. VECTOR + ENTITY RETRIEVAL
    # ========================================================

    retrieved_chunks = (
        await retrieve_chunks(
            db=db,
            tenant_id=query.tenant_id,
            query_embedding=query_embedding,
            resolved=resolved,
        )
    )

    # ========================================================
    # 8. CONTEXT
    # ========================================================

    context = build_context(
        retrieved_chunks
    )

    fallback_text = (
        tenant.fallback_message
        or (
            "Sorry, I don't have an answer "
            "for that — try rephrasing or "
            "contact support."
        )
    )

    # ========================================================
    # 9. CHECK "ANYTHING ELSE?"
    # ========================================================

    no_more_items = False

    if (
        resolved.intent
        == QueryIntent.continuation
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
                        CAST(
                            :session_id
                            AS uuid
                        )
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
                prior_sources_result
                .fetchall()
            )
        }

        retrieved_ids = {
            str(
                c["chunk_id"]
            )
            for c in retrieved_chunks
        }

        new_chunk_ids = (
            retrieved_ids
            - already_cited_ids
        )

        no_more_items = (
            bool(already_cited_ids)
            and not new_chunk_ids
        )

    # ========================================================
    # 10. ANSWER PROMPT
    # ========================================================

    if no_more_items:

        system_prompt = f"""
You are {tenant.bot_name or "a helpful AI assistant"},
a support assistant for this business.

The user is asking whether there are any other products,
options, or items beyond what was already discussed.

The retrieved context contains no new items beyond the
products/options already discussed.

Reply with ONE short, warm sentence confirming that those
are all the currently available options in that category.

Do not apologize.

Do not say you don't understand.

Do not ask the user to rephrase.

Do not invent anything.
"""

    else:

        if (
            resolved.intent
            == QueryIntent.comparison
        ):

            task_instruction = """
This is a COMPARISON question.

You MUST compare the relevant products using the requested
attribute.

For example:

"most expensive"
→ compare prices

"cheapest"
→ compare prices

"maximum area coverage"
→ compare area coverage

"lowest power"
→ compare power

IMPORTANT:

Do NOT select the product whose chunk has the highest
vector similarity.

Actually inspect the retrieved product information.

If a comparison cannot be established from the retrieved
context, use the fallback message.
"""

        elif (
            resolved.intent
            == QueryIntent.summary
        ):

            task_instruction = """
This is a SUMMARY request.

Summarize the requested entity or products.

If the user said "summarize it", use the resolved entity
from the Resolved Query.

Combine information from multiple retrieved chunks when
necessary.

Do not introduce unrelated products.
"""

        elif (
            resolved.intent
            == QueryIntent.catalog
            or resolved.requires_all_products
        ):

            task_instruction = """
This is a CATALOG / ALL-PRODUCTS request.

Produce a comprehensive bullet-point list of the relevant
products/items found in Retrieved Context.

Use ALL relevant retrieved information.

Do not invent products.

Do not omit products merely because one product's chunk
has a lower vector similarity.
"""

        elif (
            resolved.intent
            == QueryIntent.multi_entity_attribute
        ):

            task_instruction = """
The user is asking for an attribute across multiple
products.

Return each relevant product and its corresponding
attribute.

Do not invent missing values.

If a product does not have the requested attribute in the
retrieved context, do not make up a value.
"""

        elif (
            resolved.intent
            == QueryIntent.attribute_lookup
        ):

            task_instruction = """
This is an ATTRIBUTE LOOKUP.

Answer the requested attribute for the entity identified
in the Resolved Query.

If the user used "it", "this", "that product", "their",
etc., use the resolved entity.

Do NOT switch to another product merely because another
chunk has a higher similarity score.
"""

        elif (
            resolved.intent
            == QueryIntent.clarification
        ):

            task_instruction = """
This is a clarification/follow-up request.

Use the Resolved Query to determine what the user is
referring to.

Answer only from Retrieved Context.
"""

        else:

            task_instruction = """
Answer the user's question using the Retrieved Context.
"""

        system_prompt = f"""
You are {tenant.bot_name or "a helpful AI assistant"},
a support assistant for this business.

Use plain, clear, conversational language.

Default to 2-5 short sentences.

{task_instruction}

STRICT CONTEXT RULE:

You may ONLY use factual information explicitly present
in Retrieved Context.

Conversation history may be used to resolve references
such as:

- it
- its
- they
- their
- this
- that
- these
- those
- the other one

Conversation history is NOT an independent source of facts.

Never invent:

- products
- prices
- specifications
- features
- measurements
- availability
- rankings
- product comparisons

If the requested information cannot be established from
Retrieved Context, output EXACTLY:

"{fallback_text}"

and nothing else.
"""

    # ========================================================
    # 11. LLM MESSAGES
    # ========================================================

    llm_messages = [
        {
            "role": "system",
            "content": system_prompt,
        }
    ]

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

    user_prompt = f"""
Resolved Query:
{resolved.model_dump_json()}

Retrieved Context:
{context}

Current User Question:
{query.question}
"""

    llm_messages.append(
        {
            "role": "user",
            "content": user_prompt,
        }
    )

    # ========================================================
    # 12. ANSWER GENERATION
    # ========================================================

    completion = (
        groq_client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=llm_messages,
            temperature=0,
        )
    )

    answer = (
        completion
        .choices[0]
        .message
        .content
        .strip()
    )

    # ========================================================
    # 13. SAVE USER MESSAGE
    # ========================================================

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

    # ========================================================
    # 14. SAVE BOT MESSAGE
    # ========================================================

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

    # ========================================================
    # 15. SAVE SOURCES
    # ========================================================

    sources = []

    if (
        retrieved_chunks
        and answer.strip()
        != fallback_text.strip()
        and not no_more_items
    ):

        source_rows = []

        for chunk in retrieved_chunks:

            source_rows.append(
                {
                    "message_id":
                        bot_message_id,

                    "chunk_id":
                        chunk["chunk_id"],

                    "relevance_score":
                        chunk["similarity"],
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

    # ========================================================
    # 16. COMMIT
    # ========================================================

    await db.commit()

    return ChatResponse(
        session_id=str(
            session_id
        ),
        answer=answer,
        sources=sources,
    )


# ============================================================
# END CHAT
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

@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    return {"status": "ok"}
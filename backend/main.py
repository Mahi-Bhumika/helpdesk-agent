from fastapi import UploadFile, File, Form
import tempfile
import os as os_module

import time

from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db

from extract_text import extract_text
from chunking import chunk_text, embed_chunks

from groq import Groq

from rate_limit import enforce_chat_rate_limit

import asyncio

from auth import get_current_user, decode_jwt

from fastapi import FastAPI, HTTPException, Depends, Header, Query

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
    id: Optional[int] = None
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
    file_url: Optional[str] = None
    format: Optional[str] = None
    theme: Optional[str] = None
    status: Optional[str] = None


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



# POST — create a new document
class DocumentCreate(BaseModel):
    tenant_id: str
    file_url: Optional[str] = None
    format: Optional[str] = None
    theme: Optional[str] = None


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
    type_of_business: Optional[str] = None
    subscription_plan: Optional[str] = None
    bot_name: Optional[str] = None
    greeting_message: Optional[str] = None
    theme_color: Optional[str] = None
    fallback_message: Optional[str] = None


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


import re

from urllib.parse import urlparse

def extract_origin(url_or_domain: str) -> str:
    """
    Normalizes whatever got saved in website_domain — a bare domain,
    a full URL, or a URL with a path — down to just scheme://host,
    matching the exact format browsers send in the Origin header.
    """
    if not url_or_domain:
        return ""
    if not url_or_domain.startswith(("http://", "https://")):
        url_or_domain = "https://" + url_or_domain
    parsed = urlparse(url_or_domain)
    return f"{parsed.scheme}://{parsed.netloc}"

_GREETING_PATTERNS = re.compile(
    r"^\s*(hi|hii+|hey|hello|yo|sup|good\s?(morning|afternoon|evening)|howdy|hola)\s*[!.?]*\s*$",
    re.IGNORECASE,
)

_ACKNOWLEDGMENT_PATTERNS = re.compile(
    r"^\s*(thanks?|thank\s?you+|thx|ty|tysm|ok(ay)?|okie|got\s?it|cool|great|perfect|"
    r"alright|sounds\s?good|awesome|nice(\s?one)?|sure|no\s?problem|np)\s*[!.?]*\s*$",
    re.IGNORECASE,
)

def classify_smalltalk(question: str) -> Optional[str]:
    """
    Detects short messages that shouldn't go through retrieval at all.
    Returns 'greeting', 'acknowledgment', or None (meaning: run retrieval
    normally). Kept as two categories, not one, because they need
    different canned replies — repeating the greeting message back at
    someone who just said "thanks" reads as broken, not helpful.
    """
    q = question.strip()
    if len(q) > 25:
        return None
    if _GREETING_PATTERNS.match(q):
        return "greeting"
    if _ACKNOWLEDGMENT_PATTERNS.match(q):
        return "acknowledgment"
    return None


SHORT_QUESTION_CHAR_LIMIT = 40

def _needs_query_rewrite(question: str, history_rows: list) -> bool:
    """
    Decides whether the retrieval query needs rewriting before embedding.

    Deliberately NOT keyword-based. A fixed phrase list ("tell me more",
    "what else") will always miss real phrasings people actually type —
    "how much?", "the price?", "yes please" are all genuine follow-ups
    that depend entirely on the previous turn, and none of them match any
    reasonable keyword list. Triggering on message SHAPE (short + a real
    conversation already exists) instead of specific words covers all of
    these, and anything else worded just as briefly, without needing to
    predict the exact wording in advance.

    A short but genuinely standalone new question ("refund policy?") will
    also trigger this — that's an accepted, safe tradeoff: the rewrite
    prompt below is explicitly instructed to leave already-standalone
    questions unchanged, so the cost is one extra fast LLM call, not a
    wrong answer.
    """
    if not history_rows:
        return False
    return len(question.strip()) <= SHORT_QUESTION_CHAR_LIMIT


def _rewrite_query_for_retrieval(question: str, history_rows: list) -> str:
    """
    Uses one fast Groq call to turn a short, context-dependent question
    into a standalone search query, using the recent conversation for
    context — e.g. "how much?" after a message about the Summit 400
    becomes "What is the price of the Summit 400 headphones?" before
    being embedded for pgvector search.

    This ONLY affects what gets embedded and searched. The LLM that
    generates the actual user-facing answer still sees the real, original
    question text — this step exists purely to fix retrieval, not to
    change what the bot appears to have been asked.

    Falls back to the raw question on any failure (network hiccup, rate
    limit, malformed response) rather than letting a non-critical
    enhancement step turn into a new source of /chat errors.
    """
    history_text = "\n".join(f"{h.sender}: {h.content}" for h in history_rows)
    rewrite_prompt = (
        "Rewrite the user's latest message into a short, standalone search "
        "query, using the conversation history to fill in anything it "
        "depends on (a product name, a topic, what 'it' or 'that' refers "
        "to). Output ONLY the rewritten query — no quotes, no explanation. "
        "If the message is already standalone and doesn't depend on the "
        "history, output it unchanged.\n\n"
        f"Conversation history:\n{history_text}\n\n"
        f"Latest message: {question}\n\n"
        "Standalone search query:"
    )
    try:
        completion = groq_client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[{"role": "user", "content": rewrite_prompt}],
            max_tokens=60,
            temperature=0,
        )
        rewritten = (completion.choices[0].message.content or "").strip().strip('"')
        return rewritten if rewritten else question
    except Exception as e:
        print(f"[DEBUG] Query rewrite failed, using raw question instead: {e}")
        return question


_ENUMERATION_PATTERNS = re.compile(
    r"(full\s?list|list\s?(of\s?)?(all|every)|everything\s?(you|there\s?is)|"
    r"all\s?(of\s?)?(your|the)?\s?(products?|items?|services?|plans?|options?|features?)|"
    r"complete\s?list|show\s?me\s?(all|everything)|"
    r"what\s?(products?|items?|services?|plans?)\s?do\s?you\s?(have|offer|sell|provide)|"
    r"everything\s?(you\s?)?(have|offer|sell))",
    re.IGNORECASE,
)

def is_enumeration_query(question: str) -> bool:
    """
    Detects broad "give me everything" style questions ("full list of all
    products", "what services do you offer"). Deliberately NOT
    length-capped — these can be phrased naturally at any length ("gimme
    a full list of all products" is well over the 40-char rewrite
    threshold above). Uses search() rather than match() since the
    trigger phrase can appear anywhere in the sentence, not just at the
    start.

    Vector similarity search is structurally the wrong tool for this
    shape of question: it finds the single most semantically similar
    chunk(s) to the literal query text, but an exhaustive answer usually
    needs many chunks that are each only weakly similar to the phrase
    "full list of all products" on their own (a chunk about one specific
    item rarely scores high against that exact wording). The normal
    top_k=5 + 0.35-threshold search is tuned for precision on a single
    fact, not coverage across a whole catalog — so it needs a separate,
    much wider retrieval pass rather than a parameter tweak to the
    existing one.
    """
    return bool(_ENUMERATION_PATTERNS.search(question))


class ChatSource(BaseModel):
    chunk_id: str
    relevance_score: float

class ChatQuery(BaseModel):
    tenant_id: str
    question: str
    session_id: Optional[str] = None
    top_k: int = 5

class ChatResponse(BaseModel):
    session_id: str
    answer: str
    sources: List[ChatSource]

SIMILARITY_THRESHOLD = 0.35
ENUMERATION_TOP_K = 25
ENUMERATION_SIMILARITY_THRESHOLD = 0.15


# --- Helper Functions ---

def classify_smalltalk(question: str) -> Optional[str]:
    """
    Classifies strict standalone smalltalk.
    If the question contains follow-up intents (e.g. 'cool how much?'),
    it returns None so it can be handled by the RAG pipeline.
    """
    cleaned = question.strip().lower().rstrip("!.,?")
    greetings = {"hi", "hello", "hey", "good morning", "good evening"}
    acknowledgments = {"thanks", "thank you", "cool", "ok", "okay", "got it"}

    if cleaned in greetings:
        return "greeting"
    if cleaned in acknowledgments:
        return "acknowledgment"
    return None


def _needs_query_rewrite(question: str, history_rows: list) -> bool:
    """
    Determines if the question depends on conversation history to make sense.
    """
    if not history_rows:
        return False

    q_lower = question.strip().lower()
    followup_triggers = [
        "tell me more", "more details", "how much", "price", "cost",
        "and the other", "what about", "the other one", "both", "this",
        "that", "these", "it", "how much is it", "cool how much"
    ]

    if any(trigger in q_lower for trigger in followup_triggers):
        return True

    return len(q_lower.split()) <= 5


def _rewrite_query_for_retrieval(question: str, history_rows: list) -> str:
    """
    Uses an LLM turn to resolve pronouns and implicit references into a
    standalone vector search query.
    """
    history_str = "\n".join([
        f"{'User' if h.sender == 'user' else 'Assistant'}: {h.content}"
        for h in history_rows[-4:]
    ])

    rewrite_prompt = [
        {
            "role": "system",
            "content": (
                "You are a search query reformulation module. Given a conversation history and a follow-up user message, "
                "rephrase the follow-up message into a complete, standalone search query containing all necessary product "
                "names and specifics from history. Output ONLY the rephrased search query, nothing else."
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
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[DEBUG] Query rewrite failed: {e}")
        return question


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

    # 3. Smalltalk Check
    smalltalk_kind = classify_smalltalk(query.question)
    if smalltalk_kind:
        reply = (
            tenant.greeting_message or "Hello! How can I help you today?"
            if smalltalk_kind == "greeting"
            else "You're welcome! Let me know if there's anything else I can help with."
        )

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

    # 4. Fetch Conversation History (Last 6 Turns)
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

    # 5. Query Rewriting & Embedding Strategy
    is_enum = is_enumeration_query(query.question)
    retrieval_query_text = query.question

    if not is_enum and _needs_query_rewrite(query.question, history_rows):
        retrieval_query_text = _rewrite_query_for_retrieval(query.question, history_rows)
        print(f"[DEBUG] Rewritten query for vector search: '{retrieval_query_text}'")

    query_embedding = embed_chunks([retrieval_query_text])[0]
    effective_top_k = ENUMERATION_TOP_K if is_enum else top_k
    effective_threshold = ENUMERATION_SIMILARITY_THRESHOLD if is_enum else SIMILARITY_THRESHOLD

    # 6. Vector Search Execution
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

    context = "\n\n---\n\n".join(chunk["chunk_text"] for chunk in retrieved_chunks) if retrieved_chunks else "NO_RELEVANT_CONTEXT_FOUND"
    fallback_text = tenant.fallback_message or "Sorry, I don't have an answer for that — try rephrasing or contact support."

    # 8. Construct System & User Prompts
    system_prompt = (
        f"You are {tenant.bot_name or 'a helpful AI assistant'}, a support assistant for this business. "
        "Use plain conversational language without headers, defaulting to 2-4 short sentences. Two exceptions: "
        "(1) if the question genuinely asks for a step-by-step process, a short numbered list is fine; "
        "(2) if the question asks for a list, catalog, or everything available (e.g. 'list all your "
        "products', 'what do you offer'), use all of the Retrieved Context provided to compile as complete "
        "a bullet-point list as the context actually supports — don't artificially shorten it to 2-4 "
        "sentences, and don't invent items the context doesn't mention.\n\n"
        "STRICT RULE — read carefully: You may ONLY answer using information found in the 'Retrieved Context' "
        "provided below. This applies to every kind of question, with no exceptions — factual questions, casual "
        "questions, personal questions, opinion questions, anything. You have no knowledge, opinions, preferences, "
        "or facts of your own outside that context.\n\n"
        "If the answer is not clearly present in the Retrieved Context, respond with strictly and exactly this "
        "message and nothing else, regardless of what was asked:\n"
        f'"{fallback_text}"\n\n'
        "You may use the conversation history below only to understand what a follow-up question like 'tell me "
        "more' or 'why' is referring to — never as a source of facts to answer from. If the context doesn't "
        "contain the answer, history doesn't change that; the fallback still applies."
    )

    llm_messages = [{"role": "system", "content": system_prompt}]
    for h in history_rows:
        role = "user" if h.sender == "user" else "assistant"
        llm_messages.append({"role": role, "content": h.content})

    user_prompt = f"Retrieved Context:\n{context}\n\nUser Question: {query.question}"
    llm_messages.append({"role": "user", "content": user_prompt})

    # 9. LLM Generation
    completion = groq_client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=llm_messages,
    )
    answer = completion.choices[0].message.content

    # 10. Save Current Turn to DB
    await db.execute(
        text("INSERT INTO messages (session_id, tenant_id, sender, content) VALUES (CAST(:session_id AS uuid), CAST(:tenant_id AS uuid), 'user', :content)"),
        {"session_id": session_id, "tenant_id": query.tenant_id, "content": query.question},
    )

    bot_message_result = await db.execute(
        text("INSERT INTO messages (session_id, tenant_id, sender, content) VALUES (CAST(:session_id AS uuid), CAST(:tenant_id AS uuid), 'bot', :content) RETURNING message_id"),
        {"session_id": session_id, "tenant_id": query.tenant_id, "content": answer},
    )
    bot_message_id = bot_message_result.fetchone().message_id

    # 11. Store Sources & Commit
    sources = []
    if retrieved_chunks:
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
    csat: Optional[int] = Field(None, ge=1, le=5)


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
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    min_csat: Optional[int] = Query(None),
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

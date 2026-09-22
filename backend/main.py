
from fastapi import UploadFile, File, Form
import tempfile
import os
import os as os_module  # avoid clashing with your existing `os` usage if any

import time


from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional

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

# --- CORS: allow the frontend (local + deployed) to call this backend ---
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
    if str(doc["tenant_id"]) != current_user["tenant_id"]:  # ← wrap in str()
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
    uploaded_by: Optional[str] = None
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
    result = await db.execute(query, doc.model_dump())
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
    fallback_message: Optional[str] = None  # <--- MISSING HERE

@app.get("/tenants/{tenant_id}/widget-config")
async def get_widget_config(tenant_id: str, db: AsyncSession = Depends(get_db)):
    enforce_chat_rate_limit(f"widget-config:{tenant_id}", max_requests=60, window_seconds=60.0)

    # UPDATE THIS QUERY:

    result = await db.execute(
        text("""
            SELECT bot_name, greeting_message, theme_color, fallback_message
            FROM tenants
            WHERE tenant_id = :tenant_id
        """),
        {"tenant_id": tenant_id},
    )
    tenant = result.fetchone()

    return {
        "bot_name": tenant.bot_name,
        "greeting_message": tenant.greeting_message,
        "theme_color": tenant.theme_color,
        "fallback_message": tenant.fallback_message,  # <--- MISSING HERE
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
        bot_name, greeting_message, theme_color, fallback_message  -- <--- MISSING HERE
    )
    VALUES (
        :company_name, :type_of_business, :subscription_plan, 
        :bot_name, :greeting_message, :theme_color, :fallback_message -- <--- MISSING HERE
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

    # ...rest of the function unchanged from here down    # Save the uploaded file to a temp path so pdfplumber can read it
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        contents = await file.read()
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        t0 = time.time()
        extracted_text = await asyncio.to_thread(extract_text, tmp_path)
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

def is_smalltalk(question: str) -> bool:
    """
    Detects short greeting-only messages so we can skip retrieval
    and answer naturally instead of dumping document context.
    """
    q = question.strip()
    if len(q) > 25:
        return False
    return bool(_GREETING_PATTERNS.match(q))



class ChatQuery(BaseModel):
    tenant_id: str
    session_id: Optional[str] = None
    question: str
    top_k: int = 5


class ChatSource(BaseModel):
    chunk_id: str
    relevance_score: float

class ChatResponse(BaseModel):
    session_id: str
    answer: str
    sources: list[ChatSource]
@app.post("/chat", response_model=ChatResponse)
async def chat(query: ChatQuery, origin: str = Header(None), db: AsyncSession = Depends(get_db)):
    enforce_chat_rate_limit(query.tenant_id)

    top_k = min(query.top_k, 10)  # cap to prevent an oversized retrieval query

    # Fetch tenant config with required fields
    tenant_row = await db.execute(
        text("SELECT website_domain, fallback_message, bot_name, greeting_message FROM tenants WHERE tenant_id = CAST(:tid AS uuid)"),
        {"tid": query.tenant_id},
    )
    tenant = tenant_row.fetchone()
    if not tenant or not tenant.website_domain:
        raise HTTPException(status_code=403, detail="Tenant not configured for widget access")
    if not origin or extract_origin(tenant.website_domain) != origin:
        raise HTTPException(status_code=403, detail="Origin not authorized for this tenant")

    # Step 1: Ensure session exists or create a new one
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

    # Step 2: Greeting check — BEFORE retrieval, so a "hi" never pays for
    # an embedding call or a vector search. Uses is_smalltalk() (regex,
    # handles punctuation) instead of an exact-match set.
    if is_smalltalk(query.question):
        greeting_msg = tenant.greeting_message or "Hello! How can I help you today?"

        await db.execute(
            text("INSERT INTO messages (session_id, tenant_id, sender, content) VALUES (CAST(:session_id AS uuid), CAST(:tenant_id AS uuid), 'user', :content)"),
            {"session_id": session_id, "tenant_id": query.tenant_id, "content": query.question},
        )
        await db.execute(
            text("INSERT INTO messages (session_id, tenant_id, sender, content) VALUES (CAST(:session_id AS uuid), CAST(:tenant_id AS uuid), 'bot', :content)"),
            {"session_id": session_id, "tenant_id": query.tenant_id, "content": greeting_msg},
        )
        await db.commit()

        return ChatResponse(session_id=str(session_id), answer=greeting_msg, sources=[])

    # Step 3: Fetch last 6 messages from conversation history for memory
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

    # Step 4: Query vector store using Cosine Distance operator (<=>)
    query_embedding = embed_chunks([query.question])[0]

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
        "top_k": top_k,
    })
    rows = result.fetchall()

    # Step 5: Filter chunks using Similarity Threshold
    SIMILARITY_THRESHOLD = 0.40
    retrieved_chunks = [
        dict(row._mapping) for row in rows 
        if (1 - row.distance) >= SIMILARITY_THRESHOLD
    ]

    context = "\n\n---\n\n".join(chunk["chunk_text"] for chunk in retrieved_chunks) if retrieved_chunks else "NO_RELEVANT_CONTEXT_FOUND"
    fallback_text = tenant.fallback_message or "Sorry, I don't have an answer for that — try rephrasing or contact support."

    # Step 6: Construct LLM messages with conversation memory
    system_prompt = (
        f"You are {tenant.bot_name or 'a helpful AI assistant'}, a support assistant for this business. "
        "Use plain conversational language without headers or bullet lists, defaulting to 2-4 short sentences.\n\n"
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

    completion = groq_client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=llm_messages,
    )
    answer = completion.choices[0].message.content

    # Step 7: Save current turn to DB
    await db.execute(
        text("INSERT INTO messages (session_id, tenant_id, sender, content) VALUES (CAST(:session_id AS uuid), CAST(:tenant_id AS uuid), 'user', :content)"),
        {"session_id": session_id, "tenant_id": query.tenant_id, "content": query.question},
    )

    bot_message_result = await db.execute(
        text("INSERT INTO messages (session_id, tenant_id, sender, content) VALUES (CAST(:session_id AS uuid), CAST(:tenant_id AS uuid), 'bot', :content) RETURNING message_id"),
        {"session_id": session_id, "tenant_id": query.tenant_id, "content": answer},
    )
    bot_message_id = bot_message_result.fetchone().message_id

    # Step 8: Save source references — batched in one call instead of one per chunk
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
async def end_chat(payload: EndChatRequest, db: AsyncSession = Depends(get_db)):
    # Verify session exists
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

    # Update status, save csat, and set ending timestamp
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

from pydantic import BaseModel

class FeedbackPayload(BaseModel):
    session_id: str
    rating: int  # 1 to 5

@app.post("/chat/feedback")
async def record_feedback(
    payload: FeedbackPayload,
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        text("""
            UPDATE chat_sessions
            SET 
                customer_satisfaction = :rating,
                end_datetime = NOW()
            WHERE session_id = CAST(:session_id AS uuid)
        """),
        {"session_id": payload.session_id, "rating": payload.rating},
    )
    await db.commit()
    return {"status": "success"}

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
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query_str = """
        SELECT
            cs.session_id,
            cs.start_datetime,
            cs.end_datetime,
            cs.customer_satisfaction,
            COUNT(m.message_id) AS message_count,
            MAX(m.created_at) AS last_message_at
        FROM chat_sessions cs
        LEFT JOIN messages m ON m.session_id = cs.session_id
        WHERE cs.tenant_id = CAST(:tenant_id AS uuid)
    """
    params = {"tenant_id": current_user["tenant_id"]}

    if start_date:
        query_str += " AND cs.start_datetime >= :start_date::timestamp"
        params["start_date"] = start_date
    if end_date:
        query_str += " AND cs.start_datetime <= :end_date::timestamp"
        params["end_date"] = end_date
    if min_csat:
        query_str += " AND cs.customer_satisfaction >= :min_csat"
        params["min_csat"] = min_csat

    query_str += """
        GROUP BY cs.session_id
        ORDER BY cs.start_datetime DESC
        LIMIT 100
    """

    result = await db.execute(text(query_str), params)
    rows = result.fetchall()
    return [dict(row._mapping) for row in rows]


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
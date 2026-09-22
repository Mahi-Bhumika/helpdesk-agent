
from fastapi import UploadFile, File, Form
import tempfile
import os
import os as os_module  # avoid clashing with your existing `os` usage if any

import time


from fastapi import FastAPI, HTTPException, Depends, Header
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

    # Fetch tenant config: needed for the Origin check and the fallback message
    tenant_row = await db.execute(
        text("SELECT website_domain, fallback_message FROM tenants WHERE tenant_id = :tid"),
        {"tid": query.tenant_id},
    )
    tenant = tenant_row.fetchone()
    if not tenant or not tenant.website_domain:
        raise HTTPException(status_code=403, detail="Tenant not configured for widget access")
    if not origin or extract_origin(tenant.website_domain) != origin:
        raise HTTPException(status_code=403, detail="Origin not authorized for this tenant")
    
# Step 1: Create session if missing
    session_id = query.session_id
    if session_id is None:
        session_result = await db.execute(
            text("""
                INSERT INTO chat_sessions (tenant_id)
                VALUES (:tenant_id)
                RETURNING session_id
            """),
            {"tenant_id": query.tenant_id},
        )
        session_id = str(session_result.fetchone().session_id)

    # Step 2: Query vector store FIRST
    query_embedding = embed_chunks([query.question])[0]

    search_query = text("""
        SELECT chunk_id, chunk_text, chunk_index, document_id, embedding <-> :query_embedding AS distance
        FROM document_chunks
        WHERE tenant_id = :tenant_id
        ORDER BY embedding <-> :query_embedding
        LIMIT :top_k
    """)
    result = await db.execute(search_query, {
        "query_embedding": str(query_embedding),
        "tenant_id": query.tenant_id,
        "top_k": query.top_k,
    })
    rows = result.fetchall()

    # Step 3: Filter chunks using Similarity (1.0 = exact match)
    # Lowering to 0.40–0.45 ensures short valid questions pass through safely
    SIMILARITY_THRESHOLD = 0.40

    retrieved_chunks = [
        dict(row._mapping) for row in rows 
        if getattr(row, "relevance_score", 1 - row.distance) >= SIMILARITY_THRESHOLD
    ]

    context = "\n\n---\n\n".join(chunk["chunk_text"] for chunk in retrieved_chunks) if retrieved_chunks else "NO_RELEVANT_CONTEXT_FOUND"
    fallback_text = tenant.fallback_message or "Sorry, I don't have an answer for that — try rephrasing or contact support."
    # Step 4: Prompt and LLM completion

    GREETINGS = {
    # Basic & Casual
    "hi", "hii", "hiii", "hiiii", "hello", "helloo", "hey", "heyy", "heyyy",
    "heyya", "yo", "yoo", "sup", "whats up", "what's up", "wbu", "wyd",
    
    # Formal & Time-based
    "good morning", "good afternoon", "good evening", "good day", "greetings",
    
    # Conversational Openers
    "howdy", "hiya", "hola", "bonjour", "namaste", "salutations",
    "are you there", "anyone there", "anyone here", "is anyone there",
    
    # Common Questions / Check-ins
    "how are you", "how are you doing", "hows it going", "how's it going",
    "how are things", "what can you do", "who are you", "what is your name",
    "help", "can you help me", "i need help", "start", "menu"
}
    user_message = query.question.strip().lower()

    # Check for simple greetings
    if user_message in GREETINGS:
        bot_name = tenant.bot_name or "Assistant"
        greeting_msg = tenant.greeting_message or f"Hello! How can I help you today?"
        return {"response": greeting_msg, "sources": []}
    
    system_prompt = (
    f"You are {tenant.bot_name or 'a helpful AI assistant'}. "
    "Use plain conversational language without headers or bullet lists, defaulting to 2-4 short sentences.\n\n"
    
    "RULES:\n"
    "1. SMALL TALK / GREETINGS: If the user message is a simple greeting, greeting response, or polite small talk "
    "(e.g., 'hi', 'hello', 'how are you', 'thank you'), reply naturally, politely, and welcome them without using the context. "
    "Do NOT trigger the fallback message for greetings.\n\n"
    
    "2. FACTUAL / PRODUCT QUESTIONS: For actual questions, base your response ONLY on the provided context below.\n"
    "   - Exception: If the question asks for a process or steps (e.g. 'how do I reset my password'), "
    "you may use a short numbered list — keeping each step to one short line.\n"
    f'   - If the context is NO_RELEVANT_CONTEXT_FOUND or the answer isn\'t in the context, respond strictly and exactly with: "{fallback_text}"\n\n'
    
    "3. FOLLOW-UPS: After answering, if there's likely more relevant detail in the context "
    "(pricing, specs, related items), briefly invite the user to ask — e.g., 'Want to know about pricing or colors?' "
    "Skip this if the answer is already complete or if responding to a greeting."
)
    user_prompt = f"Context:\n{context}\n\nQuestion: {query.question}"

    completion = groq_client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    answer = completion.choices[0].message.content

    # Step 5: Save user message
    await db.execute(
        text("""
            INSERT INTO messages (session_id, tenant_id, sender, content)
            VALUES (:session_id, :tenant_id, 'user', :content)
        """),
        {"session_id": session_id, "tenant_id": query.tenant_id, "content": query.question},
    )

    # Step 6: Save bot message
    bot_message_result = await db.execute(
        text("""
            INSERT INTO messages (session_id, tenant_id, sender, content)
            VALUES (:session_id, :tenant_id, 'bot', :content)
            RETURNING message_id
        """),
        {"session_id": session_id, "tenant_id": query.tenant_id, "content": answer},
    )
    bot_message_id = bot_message_result.fetchone().message_id

    # Step 7: Save sources using individual execution calls
    sources = []
    if retrieved_chunks:
        for chunk in retrieved_chunks:
            relevance = 1 / (1 + chunk["distance"])
            await db.execute(
                text("""
                    INSERT INTO message_sources (message_id, chunk_id, relevance_score)
                    VALUES (:message_id, :chunk_id, :relevance_score)
                """),
                {
                    "message_id": bot_message_id,
                    "chunk_id": chunk["chunk_id"],
                    "relevance_score": relevance,
                },
            )
            sources.append(
                ChatSource(chunk_id=str(chunk["chunk_id"]), relevance_score=relevance)
            )

    await db.commit()

    return ChatResponse(
        session_id=str(session_id),
        answer=answer,
        sources=sources,
    )


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
            WHERE session_id = :sid::uuid AND tenant_id = :tid::uuid
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
            WHERE session_id = :sid::uuid AND tenant_id = :tid::uuid
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
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text("""
            SELECT
                cs.session_id,
                cs.start_datetime,
                cs.end_datetime,
                cs.customer_satisfaction,
                COUNT(m.message_id) AS message_count,
                MAX(m.created_at) AS last_message_at
            FROM chat_sessions cs
            LEFT JOIN messages m ON m.session_id = cs.session_id
            WHERE cs.tenant_id = :tenant_id
            GROUP BY cs.session_id
            ORDER BY cs.start_datetime DESC
            LIMIT 100
        """),
        {"tenant_id": current_user["tenant_id"]},
    )
    rows = result.fetchall()
    return [dict(row._mapping) for row in rows]

@app.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify the session belongs to this tenant before returning anything
    session_check = await db.execute(
        text("SELECT tenant_id FROM chat_sessions WHERE session_id = :session_id"),
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
            WHERE session_id = :session_id
            ORDER BY created_at ASC
        """),
        {"session_id": session_id},
    )
    messages = [dict(row._mapping) for row in messages_result.fetchall()]

    sources_result = await db.execute(
        text("""
            SELECT ms.message_id, dc.chunk_text, dc.chunk_index, ms.relevance_score
            FROM message_sources ms
            JOIN document_chunks dc ON dc.chunk_id = ms.chunk_id
            WHERE ms.message_id = ANY(:message_ids)
            ORDER BY ms.relevance_score DESC
        """),
        {"message_ids": [m["message_id"] for m in messages]},
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
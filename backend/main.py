
from fastapi import UploadFile, File, Form
import tempfile
import os
import os as os_module  # avoid clashing with your existing `os` usage if any

import time


from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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
    allow_methods=["GET", "POST"],
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
    owner_email: str          # ← new
    company_name: str
    type_of_business: Optional[str] = None
    subscription_plan: Optional[str] = None
    bot_name: Optional[str] = None
    greeting_message: Optional[str] = None
    theme_color: Optional[str] = None


@app.post("/tenants")
async def create_tenant(
    tenant: TenantCreate,
    verified_user_id: str = Depends(decode_jwt),
    db: AsyncSession = Depends(get_db),
):
    if tenant.owner_id != verified_user_id:
        raise HTTPException(status_code=403, detail="owner_id does not match authenticated user")

    tenant_query = text("""
        INSERT INTO tenants (company_name, type_of_business, subscription_plan, bot_name, greeting_message, theme_color)
        VALUES (:company_name, :type_of_business, :subscription_plan, :bot_name, :greeting_message, :theme_color)
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

    tenant_row = await db.execute(
        text("SELECT website_domain FROM tenants WHERE tenant_id = :tid"),
        {"tid": query.tenant_id},
    )
    tenant = tenant_row.fetchone()
    if not tenant or not tenant.website_domain:
        raise HTTPException(status_code=403, detail="Tenant not configured for widget access")
    if not origin or tenant.website_domain not in origin:
        raise HTTPException(status_code=403, detail="Origin not authorized for this tenant")

    # ...rest unchanged
    # Step 1: create a session if this is the first message
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

    # Step 2: embed the query and retrieve relevant chunks
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
    retrieved_chunks = [dict(row._mapping) for row in rows]

    # Step 3: build context and call the LLM
    context = "\n\n---\n\n".join(chunk["chunk_text"] for chunk in retrieved_chunks)

    system_prompt = (
        "You are a helpful assistant answering questions based only on the provided context. "
        "If the answer isn't in the context, say you don't have that information. "
        "Do not make up information beyond what's given."
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

    # Step 4: log the user's message
    await db.execute(
        text("""
            INSERT INTO messages (session_id, tenant_id, sender, content)
            VALUES (:session_id, :tenant_id, 'user', :content)
        """),
        {"session_id": session_id, "tenant_id": query.tenant_id, "content": query.question},
    )

    # Step 5: log the bot's message, get its id
    bot_message_result = await db.execute(
        text("""
            INSERT INTO messages (session_id, tenant_id, sender, content)
            VALUES (:session_id, :tenant_id, 'bot', :content)
            RETURNING message_id
        """),
        {"session_id": session_id, "tenant_id": query.tenant_id, "content": answer},
    )
    bot_message_id = bot_message_result.fetchone().message_id

    # Step 6: log which chunks contributed to this answer
    sources = []
    if retrieved_chunks:
        source_rows = [
            {
                "message_id": bot_message_id,
                "chunk_id": chunk["chunk_id"],
                "relevance_score": 1 / (1 + chunk["distance"]),  # convert distance to a 0-1 relevance score
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
            ChatSource(chunk_id=str(row["chunk_id"]), relevance_score=1 / (1 + row["distance"]))
            for row in retrieved_chunks
        ]

    await db.commit()

    return ChatResponse(session_id=str(session_id), answer=answer, sources=sources)

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
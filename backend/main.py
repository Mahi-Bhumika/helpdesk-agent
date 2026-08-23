
from fastapi import UploadFile, File, Form
import tempfile
import os
import os as os_module  # avoid clashing with your existing `os` usage if any


from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db

from extract_text import extract_text
from chunking import chunk_text, embed_chunks

from groq import Groq

groq_client = Groq(api_key=os_module.getenv("GROQ_API_KEY"))

app = FastAPI()

# --- CORS: allow the frontend (local + deployed) to call this backend ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://helpdesk-agent-mahi-bhumika.vercel.app"],
    allow_methods=["*"],
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
async def get_document(document_id: str, db: AsyncSession = Depends(get_db)):
    query = text("SELECT * FROM documents WHERE document_id = :document_id")
    result = await db.execute(query, {"document_id": document_id})
    row = result.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return dict(row._mapping)


class DocumentUpdate(BaseModel):
    file_url: Optional[str] = None
    format: Optional[str] = None
    theme: Optional[str] = None
    status: Optional[str] = None


@app.put("/documents/{document_id}")
async def update_document(document_id: str, doc: DocumentUpdate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        text("SELECT document_id FROM documents WHERE document_id = :document_id"),
        {"document_id": document_id}
    )
    if existing.fetchone() is None:
        raise HTTPException(status_code=404, detail="Document not found")

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
async def create_document(doc: DocumentCreate, db: AsyncSession = Depends(get_db)):
    query = text("""
        INSERT INTO documents (tenant_id, uploaded_by, file_url, format, theme)
        VALUES (:tenant_id, :uploaded_by, :file_url, :format, :theme)
        RETURNING document_id, tenant_id, status, created_at
    """)
    result = await db.execute(query, doc.model_dump())
    await db.commit()
    new_row = result.fetchone()
    return dict(new_row._mapping)





@app.get("/db-check")
async def db_check(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT 1"))
    return {"database_connected": result.scalar() == 1}


# --- Pydantic model matching the tenants table ---
class TenantCreate(BaseModel):
    company_name: str
    type_of_business: Optional[str] = None
    subscription_plan: Optional[str] = None
    bot_name: Optional[str] = None
    greeting_message: Optional[str] = None
    theme_color: Optional[str] = None


@app.post("/tenants")
async def create_tenant(tenant: TenantCreate, db: AsyncSession = Depends(get_db)):
    query = text("""
        INSERT INTO tenants (company_name, type_of_business, subscription_plan, bot_name, greeting_message, theme_color)
        VALUES (:company_name, :type_of_business, :subscription_plan, :bot_name, :greeting_message, :theme_color)
        RETURNING tenant_id, company_name, invite_token, created_at
    """)
    result = await db.execute(query, tenant.model_dump())
    await db.commit()
    new_row = result.fetchone()
    return dict(new_row._mapping)


@app.post("/kb/upload")
async def upload_document(
    document_id: str = Form(...),
    tenant_id: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    # Save the uploaded file to a temp path so pdfplumber can read it
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        contents = await file.read()
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        # Reuse your existing pipeline functions
        extracted_text = extract_text(tmp_path)
        chunks = chunk_text(extracted_text, chunk_size=250, overlap=40)
        embeddings = embed_chunks(chunks)

        insert_query = text("""
            INSERT INTO document_chunks (document_id, tenant_id, chunk_text, embedding, chunk_index)
            VALUES (:document_id, :tenant_id, :chunk_text, :embedding, :chunk_index)
        """)

        for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            await db.execute(insert_query, {
                "document_id": document_id,
                "tenant_id": tenant_id,
                "chunk_text": chunk,
                "embedding": str(emb),
                "chunk_index": idx,
            })

        await db.execute(
            text("UPDATE documents SET status = 'ready' WHERE document_id = :document_id"),
            {"document_id": document_id}
        )

        await db.commit()

    finally:
        os_module.remove(tmp_path)

    return {
        "document_id": document_id,
        "chunks_inserted": len(chunks),
    }

class ChatQuery(BaseModel):
    tenant_id: str
    question: str
    top_k: int = 5

class ChatResponse(BaseModel):
    answer: str
    sources: list[dict]

@app.post("/chat")
async def chat(query: ChatQuery, db: AsyncSession = Depends(get_db)):
    query_embedding = embed_chunks([query.question])[0]

    search_query = text("""
        SELECT chunk_text, chunk_index, document_id, embedding <-> :query_embedding AS distance
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

    # Assemble context from retrieved chunks
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

    return {
        "question": query.question,
        "answer": answer,
        "retrieved_chunks": retrieved_chunks,
    }
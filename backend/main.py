from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from database import get_db

app = FastAPI()

# --- Pydantic model: defines the "shape" of a Document ---
class Document(BaseModel):
    id: Optional[int] = None
    title: str
    content: str

# --- fake in-memory "database" for now (real Postgres comes in Week 2) ---
fake_db = {}
next_id = 1

@app.get("/")
def read_root():
    return {"status": "ok"}

# GET — fetch a document by id
@app.get("/documents/{doc_id}")
def get_document(doc_id: int):
    if doc_id not in fake_db:
        raise HTTPException(status_code=404, detail="Document not found")
    return fake_db[doc_id]

# POST — create a new document
@app.post("/documents")
def create_document(doc: Document):
    global next_id
    doc.id = next_id
    fake_db[next_id] = doc
    next_id += 1
    return doc

# PUT — update an existing document
@app.put("/documents/{doc_id}")
def update_document(doc_id: int, doc: Document):
    if doc_id not in fake_db:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.id = doc_id
    fake_db[doc_id] = doc
    return doc

@app.get("/db-check")
async def db_check(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT 1"))
    return {"database_connected": result.scalar() == 1}

from pydantic import BaseModel
from typing import Optional

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
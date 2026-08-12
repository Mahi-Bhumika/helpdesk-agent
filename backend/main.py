from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

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
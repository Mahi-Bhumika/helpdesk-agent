import requests
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('.env.local')

def create_document():
    url = f"{os.getenv('API_BASE_URL')}/documents"
    payload = {
        "tenant_id" : f"{os.getenv("TENANT_ID")}",
        "uploaded_by" : f"{os.getenv("USER_ID")}",
        "file_url" : f"{os.getenv("PDF_PATH")}",
        "format" : "pdf",
        "theme" : "doc",
    }
    response = requests.post(url, json = payload)

    print(f"[create_document] Status code : {response.status_code}")
    response.raise_for_status()
    body = response.json()
    print(f"[create_document] response JSON : {body}")
    return body

def upload_pdf(document_id):
    #uploads the pdf to the /kb/upload function
    url = f"{os.getenv("API_BASE_URL")}/kb/upload"
    with open(f"{os.getenv("PDF_PATH")}", "rb") as f:
        files = {"file": (f"{os.getenv("PDF_PATH")}", f, "application/pdf")}
        data = {"tenant_id": f"{os.getenv("TENANT_ID")}", "document_id" : document_id}
        response = requests.post(url, files=files, data=data)

    print(f"Status code: {response.status_code}")
    # raise_for_status : loudly stops execution and throws error if status is of fail/issue
    response.raise_for_status()  
    body = response.json()
    print("Response JSON:", body)
    return body


def check_chunks_in_db(document_id):
    # a connection to the supabase project
    supabase = create_client(f"{os.getenv("SUPABASE_URL")}", f"{os.getenv("SUPABASE_KEY}")}")
    result = (
        supabase.table("document_chunks")
        .select("chunk_id, chunk_index, embedding")
        .eq("document_id", document_id) #equals
        .execute()
    )
    #result is the object supabase sent, data is the list of the query output
    return result.data


def run_test():
    create_response =  create_document()
    document_id = create_response.get("document_id")

    if (not document_id) :
        print("DOCUMENT ID FETCH FAILED!")
        return
    
    upload_response = upload_pdf(document_id)
    expected_chunk_count = upload_response.get("chunk_count")

    #Step 2 : check db 
    rows = check_chunks_in_db(document_id)
    actual_chunk_count = len(rows)
    null_embeddings = [r["chunk_id"] for r in rows if r.get("embedding") is None]

    # --- Step 3: compare ---
    print("\nRESULTS")
    print(f"Expected chunks (from API response): {expected_chunk_count}")
    print(f"Actual chunks (in document_chunks):  {actual_chunk_count}")
    print(f"Rows with null embedding:             {len(null_embeddings)}")

    passed = True
    if expected_chunk_count is not None and expected_chunk_count != actual_chunk_count:
        print(f"❌ MISMATCH: expected {expected_chunk_count}, got {actual_chunk_count}")
        passed = False
    if null_embeddings:
        print(f"❌ NULL EMBEDDINGS in chunk_ids: {null_embeddings}")
        passed = False

    print("\nYAY PASS" if passed else "\n❌ FAIL — see above")


if __name__ == "__main__":
    run_test()
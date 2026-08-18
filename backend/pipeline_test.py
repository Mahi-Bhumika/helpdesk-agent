import pdfplumber
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")
tokenizer = model.tokenizer


def extract_text(pdf_path: str) -> str:
    full_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text:
                full_text.append(text)
            else:
                print(f"Warning: page {i+1} had no extractable text (likely scanned/image-based)")
    return "\n\n".join(full_text)


def chunk_text(text: str, chunk_size: int = 250, overlap: int = 40) -> list[str]:
    token_ids = tokenizer.encode(text, add_special_tokens=False)
    if not token_ids:
        return []

    chunks = []
    start = 0
    while start < len(token_ids):
        end = start + chunk_size
        chunk_ids = token_ids[start:end]
        chunks.append(tokenizer.decode(chunk_ids))
        if end >= len(token_ids):
            break
        start = end - overlap

    return chunks


def embed_chunks(chunks: list[str]) -> list[list[float]]:
    embeddings = model.encode(chunks, show_progress_bar=False)
    return embeddings.tolist()


if __name__ == "__main__":
    print("Extracting text from CPP_OOP_Notes.pdf...")
    text = extract_text("CPP_OOP_Notes.pdf")
    print(f"Total chars extracted: {len(text)}\n")

    print("Chunking (size=250, overlap=40)...")
    chunks = chunk_text(text, chunk_size=250, overlap=40)
    print(f"Number of chunks: {len(chunks)}\n")

    print("Embedding chunks...")
    embeddings = embed_chunks(chunks)
    print(f"Embedding vector length: {len(embeddings[0])}\n")

    # Sanity checks
    assert len(chunks) == len(embeddings), "Mismatch between chunk count and embedding count!"
    assert all(len(e) == 384 for e in embeddings), "Inconsistent embedding dimensions!"

    # Print first and last chunk so you can eyeball boundaries on real content
    print("--- First chunk ---")
    print(chunks[0])
    print("\n--- Last chunk ---")
    print(chunks[-1])
    print("\nAll checks passed.")
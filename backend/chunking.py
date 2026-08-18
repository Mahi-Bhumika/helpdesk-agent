from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")
tokenizer = model.tokenizer

def chunk_text(text: str, chunk_size: int = 250, overlap: int = 40) -> list[str]:
    """
    Split text into overlapping chunks, sized in real model tokens
    (using the same tokenizer as the embedding model).
    """
    token_ids = tokenizer.encode(text, add_special_tokens=False)
    if not token_ids:
        return []

    chunks = []
    start = 0
    while start < len(token_ids):
        end = start + chunk_size
        chunk_ids = token_ids[start:end]
        chunk_text_str = tokenizer.decode(chunk_ids)
        chunks.append(chunk_text_str)
        if end >= len(token_ids):
            break
        start = end - overlap

    return chunks


def embed_chunks(chunks: list[str]) -> list[list[float]]:
    embeddings = model.encode(chunks, show_progress_bar=False)
    return embeddings.tolist()


if __name__ == "__main__":
    sample_text = (
        "To reset your password, go to Settings then Account. "
        "Click Forgot Password and check your email for a reset link. "
        "The link expires after 24 hours, so use it promptly."
    )

    chunks = chunk_text(sample_text, chunk_size=15, overlap=5)  # small values just to see multiple chunks on short text
    print(f"Number of chunks: {len(chunks)}")
    for i, c in enumerate(chunks):
        print(f"\nChunk {i}: {c}")

    embeddings = embed_chunks(chunks)
    print(f"\nEmbedding vector length: {len(embeddings[0])}")
    print(f"First 5 values of chunk 0 embedding: {embeddings[0][:5]}")
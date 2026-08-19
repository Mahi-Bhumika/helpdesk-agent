from sentence_transformers import SentenceTransformer

#loading the model once at import time only
model = SentenceTransformer("all-MiniLM-L6-v2")

def get_embedding(chunks : list[str]) -> list[list[float]] :
    embedding = model.encode(chunks)
    return embedding.tolist()

#test cases to ensure the model runs fine - the if condition follows through only
#when this file is run directly and not as an embed/imported function
if (__name__ == "__main__") :
    sample_chunks = [
        "Refunds are processed withitn 5-7 business days.",
        "To request a refund, email support@company.com with your order number.",
        "Our office hours are 9am to 6pm, Monday through Friday."
    ]

    for chunk in sample_chunks:
        vec_emb = get_embedding(chunk)
        print(f"Text : {chunk[:50]}...")
        print(f"Vector length : {len(vec_emb)}")
        print(f"embedding  : {vec_emb}")
        print("_"*10)
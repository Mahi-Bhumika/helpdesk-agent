import numpy as np
import onnxruntime as ort
from transformers import AutoTokenizer
from huggingface_hub import hf_hub_download


MODEL_ID = "Xenova/all-MiniLM-L6-v2"  # pre-converted ONNX version of the same model

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
onnx_path = hf_hub_download(MODEL_ID, "onnx/model.onnx")
session = ort.InferenceSession(onnx_path)


def chunk_text(text: str, chunk_size: int = 250, overlap: int = 40, min_chunk_size: int = 20) -> list[str]:
    token_ids = tokenizer.encode(text, add_special_tokens=False)
    if not token_ids:
        return []

    chunks = []
    start = 0
    while start < len(token_ids):
        end = start + chunk_size
        chunk_ids = token_ids[start:end]

        if end >= len(token_ids) and len(chunk_ids) < min_chunk_size and chunks:
            prev_ids = tokenizer.encode(chunks[-1], add_special_tokens=False)
            merged_ids = prev_ids + chunk_ids
            chunks[-1] = tokenizer.decode(merged_ids)
            break

        chunks.append(tokenizer.decode(chunk_ids))
        if end >= len(token_ids):
            break
        start = end - overlap

    return chunks


def _mean_pooling(token_embeddings: np.ndarray, attention_mask: np.ndarray) -> np.ndarray:
    mask = attention_mask[..., None].astype(np.float32)
    summed = np.sum(token_embeddings * mask, axis=1)
    counts = np.clip(mask.sum(axis=1), a_min=1e-9, a_max=None)
    return summed / counts


def embed_chunks(chunks: list[str], batch_size: int = 16) -> list[list[float]]:
    all_embeddings = []
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        inputs = tokenizer(batch, padding=True, truncation=True, max_length=256, return_tensors="np")

        onnx_input_names = {inp.name for inp in session.get_inputs()}
        onnx_inputs = {k: v for k, v in inputs.items() if k in onnx_input_names}

        outputs = session.run(None, onnx_inputs)
        token_embeddings = outputs[0]

        batch_embeddings = _mean_pooling(token_embeddings, inputs["attention_mask"])
        norms = np.linalg.norm(batch_embeddings, axis=1, keepdims=True)
        batch_embeddings = batch_embeddings / norms

        all_embeddings.extend(batch_embeddings.tolist())

    return all_embeddings
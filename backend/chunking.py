import numpy as np
import onnxruntime as ort
from huggingface_hub import hf_hub_download
from transformers import AutoTokenizer

MODEL_ID = "Xenova/all-MiniLM-L6-v2"  # pre-converted ONNX version of the same model

# use_fast=True is required here: offset mapping (used below to slice chunk
# text out of the ORIGINAL string instead of decoding lossy token ids) is
# only available on the Rust-backed fast tokenizer, not the slow Python one.
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, use_fast=True)
if not tokenizer.is_fast:
    raise RuntimeError(
        f"'{MODEL_ID}' did not load a fast tokenizer. Offset-mapping-based chunk "
        f"extraction in chunk_text() requires a fast (Rust) tokenizer — check that "
        f"a tokenizer.json is available for this model."
    )

onnx_path = hf_hub_download(MODEL_ID, "onnx/model.onnx")
session = ort.InferenceSession(onnx_path)


def chunk_text(text: str, chunk_size: int = 250, overlap: int = 40, min_chunk_size: int = 20) -> list[str]:
    """
    Splits text into overlapping, token-sized chunks for embedding.

    Chunk *boundaries* are still determined in token space (same 250/40 window
    as before), but the chunk text that gets returned — and stored/displayed —
    is sliced directly out of the original string using each token's character
    offsets, instead of round-tripping through tokenizer.decode(). This avoids
    two problems decode() introduced: MiniLM's tokenizer is uncased (so decoded
    text came back lowercased) and drops out-of-vocabulary characters into
    literal "[UNK]" tokens on decode. Slicing the original string sidesteps
    both — an [UNK] token internally still maps to a real (start, end) character
    span, so the actual source characters come through untouched.
    """
    encoding = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
    token_ids = encoding["input_ids"]
    offsets = encoding["offset_mapping"]  # list of (start_char, end_char) per token, in `text`

    if not token_ids:
        return []

    chunks: list[str] = []
    chunk_spans: list[tuple[int, int]] = []  # parallel list of (start_char, end_char) per chunk
    n = len(token_ids)
    start = 0

    while start < n:
        end = start + chunk_size
        window_offsets = offsets[start:end]

        # Trailing chunk too small on its own — merge into the previous chunk
        # by extending the previous chunk's character span, rather than
        # re-encoding already-lossy decoded text (the old approach's second,
        # compounding source of corruption).
        if end >= n and (end - start) < min_chunk_size and chunk_spans:
            prev_start_char, _ = chunk_spans[-1]
            this_end_char = window_offsets[-1][1]
            merged_span = (prev_start_char, this_end_char)
            chunks[-1] = text[merged_span[0]:merged_span[1]].strip()
            chunk_spans[-1] = merged_span
            break

        start_char = window_offsets[0][0]
        end_char = window_offsets[-1][1]
        chunks.append(text[start_char:end_char].strip())
        chunk_spans.append((start_char, end_char))

        if end >= n:
            break
        start = end - overlap

    return chunks


def _mean_pooling(token_embeddings: np.ndarray, attention_mask: np.ndarray) -> np.ndarray:
    mask = attention_mask[..., None].astype(np.float32)
    summed = np.sum(token_embeddings * mask, axis=1)
    counts = np.clip(mask.sum(axis=1), a_min=1e-9, a_max=None)
    return summed / counts


def embed_chunks(chunks: list[str], batch_size: int = 8) -> list[list[float]]:
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
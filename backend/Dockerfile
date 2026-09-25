FROM python:3.13.7-slim

WORKDIR /app

# build-essential covers packages that need to compile (some onnxruntime/pdfplumber deps do)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install deps first (separate layer) so code edits don't force a full reinstall
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# After installing requirements.txt
RUN python -c "from transformers import AutoTokenizer; AutoTokenizer.from_pretrained('Xenova/all-MiniLM-L6-v2')"

COPY . .

EXPOSE 8000

# Shell form (not exec/array form) so ${PORT} actually gets substituted.
# Render injects PORT at runtime; locally it falls back to 8000.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
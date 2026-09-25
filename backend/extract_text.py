import logging
import sys

import pdfplumber

try:
    from PyPDF2 import PdfReader
    _PYPDF2_AVAILABLE = True
except ImportError:
    _PYPDF2_AVAILABLE = False

logger = logging.getLogger(__name__)


def _try_pypdf2_page(reader: "PdfReader", page_index: int) -> str | None:
    """Best-effort fallback for one page when pdfplumber can't extract it —
    occasionally succeeds on pages pdfplumber chokes on, for reasons specific
    to how each library parses malformed PDF structure."""
    if not _PYPDF2_AVAILABLE:
        return None
    try:
        page_text = reader.pages[page_index].extract_text()
        return page_text if page_text else None
    except Exception: # noqa: BLE001
        return None


def extract_text(pdf_path: str) -> str:
    """
    Extracts text from a PDF, page by page, with a PyPDF2 fallback for pages
    pdfplumber can't read. Pages that remain unrecoverable (typically
    scanned/image-only — OCR is not attempted) are logged and skipped.

    Raises ValueError if the file can't be opened at all (corrupted, encrypted,
    not a valid PDF), or if every single page comes back empty — both are
    real failures the caller should surface to the uploader, not silently
    treat as "zero chunks, upload succeeded."
    """
    try:
        pdf = pdfplumber.open(pdf_path)
    except Exception as e:
        raise ValueError(f"Could not open '{pdf_path}' as a PDF: {e}") from e

    pypdf2_reader = None
    if _PYPDF2_AVAILABLE:
        try:
            pypdf2_reader = PdfReader(pdf_path)
        except Exception: # noqa: BLE001
            pypdf2_reader = None  # fallback simply unavailable for this file; not fatal

    full_text = []
    failed_pages = []

    with pdf:
        total_pages = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text:
                full_text.append(text)
                continue

            fallback_text = _try_pypdf2_page(pypdf2_reader, i) if pypdf2_reader else None
            if fallback_text:
                full_text.append(fallback_text)
                logger.info("Page %d recovered via PyPDF2 fallback", i + 1)
                continue

            failed_pages.append(i + 1)
            logger.warning(
                "Page %d of %d had no extractable text (likely scanned/image-based); "
                "OCR not attempted, page skipped",
                i + 1, total_pages,
            )

    if not full_text:
        raise ValueError(
            f"No extractable text found in any of {total_pages} page(s) — this PDF is "
            f"likely fully scanned/image-based and would need OCR, which isn't supported yet."
        )

    if failed_pages:
        logger.warning(
            "Extraction completed with %d of %d page(s) skipped: %s",
            len(failed_pages), total_pages, failed_pages,
        )

    return "\n\n".join(full_text)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_text.py <path-to-pdf>")
        sys.exit(1)

    logging.basicConfig(level=logging.INFO)
    text = extract_text(sys.argv[1])
    print(text[:1000])
    print(f"\n\nTotal chars extracted: {len(text)}")
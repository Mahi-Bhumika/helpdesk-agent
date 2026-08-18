import pdfplumber

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

if __name__ == "__main__":
    text = extract_text("CPP_OOP_Notes.pdf")
    print(text[:1000])  # sanity check first 1000 chars
    print(f"\n\nTotal chars extracted: {len(text)}")
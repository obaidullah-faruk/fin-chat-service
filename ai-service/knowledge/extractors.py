import hashlib
import io
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("finchat.knowledge.extractors")

try:
    import pypdf
except ImportError:
    pypdf = None

try:
    import docx
except ImportError:
    docx = None


def normalize_text_for_hashing(text: str) -> str:
    """Normalize text by collapsing whitespace, stripping non-printable chars and lowercasing."""
    cleaned = re.sub(r"\s+", " ", text.strip().lower())
    return cleaned


def compute_content_hash(text: str) -> str:
    """Compute SHA-256 hash of normalized text to detect identical content across different files."""
    normalized = normalize_text_for_hashing(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_raw_hash(data: bytes) -> str:
    """Compute SHA-256 hash of raw binary data."""
    return hashlib.sha256(data).hexdigest()


def extract_text_from_pdf(data: bytes) -> str:
    if pypdf is None:
        raise RuntimeError("pypdf is required to extract text from PDF files.")
    reader = pypdf.PdfReader(io.BytesIO(data))
    pages_text = []
    for idx, page in enumerate(reader.pages):
        page_content = page.extract_text() or ""
        if page_content.strip():
            pages_text.append(page_content.strip())
    return "\n\n".join(pages_text)


def extract_text_from_docx(data: bytes) -> str:
    if docx is None:
        raise RuntimeError("python-docx is required to extract text from DOCX files.")
    doc = docx.Document(io.BytesIO(data))
    blocks = []
    
    # Iterate through body elements preserving order of paragraphs and tables
    for element in doc.element.body:
        if element.tag.endswith("p"):
            p = docx.text.paragraph.Paragraph(element, doc)
            text = p.text.strip()
            if text:
                blocks.append(text)
        elif element.tag.endswith("tbl"):
            tbl = docx.table.Table(element, doc)
            rows = []
            for row in tbl.rows:
                cell_texts = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                rows.append(" | ".join(cell_texts))
            if rows:
                header = rows[0]
                separator = " | ".join(["---"] * len(tbl.rows[0].cells))
                table_md = [f"| {header} |", f"| {separator} |"]
                for r in rows[1:]:
                    table_md.append(f"| {r} |")
                blocks.append("\n".join(table_md))
                
    return "\n\n".join(blocks)


def extract_text_from_json(data: bytes) -> tuple[str, str, dict[str, Any]]:
    parsed = json.loads(data.decode("utf-8"))
    if isinstance(parsed, dict):
        title = parsed.get("title", "")
        content = parsed.get("content", "")
        metadata = parsed.get("metadata", {})
        if not content:
            # Fallback if structure is generic JSON
            content = json.dumps(parsed, indent=2)
        return title, content, metadata
    return "", json.dumps(parsed, indent=2), {}


def extract_document(
    filename: str,
    data: bytes,
    default_title: str | None = None,
    category: str = "general",
) -> dict[str, Any]:
    """
    Extract text, metadata, raw file hash, and content hash from uploaded file bytes.
    Returns:
        dict containing title, text, raw_file_hash, content_hash, file_format, metadata
    """
    ext = Path(filename).suffix.lower().lstrip(".")
    raw_hash = compute_raw_hash(data)
    metadata: dict[str, Any] = {}
    title = default_title or Path(filename).stem.replace("_", " ").title()

    json_title_found = False
    if ext == "pdf":
        text = extract_text_from_pdf(data)
    elif ext in ("docx", "doc"):
        text = extract_text_from_docx(data)
    elif ext == "json":
        json_title, text, json_meta = extract_text_from_json(data)
        if json_title:
            title = json_title
            json_title_found = True
        metadata.update(json_meta)
    elif ext in ("md", "markdown", "txt"):
        text = data.decode("utf-8", errors="replace")
    else:
        # Generic text fallback
        text = data.decode("utf-8", errors="replace")

    # If first line looks like a title (# Title), extract it
    if not json_title_found:
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        if lines:
            first_line = lines[0]
            if first_line.startswith("# "):
                title = first_line.lstrip("# ").strip()
            elif not default_title and len(first_line) < 80 and not first_line.endswith("."):
                title = first_line

    content_hash = compute_content_hash(text)

    return {
        "title": title,
        "filename": filename,
        "file_format": ext or "txt",
        "category": category,
        "text": text,
        "raw_file_hash": raw_hash,
        "content_hash": content_hash,
        "metadata": metadata,
    }

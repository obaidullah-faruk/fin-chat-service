import re
from typing import Any

_HEADER_PATTERN = re.compile(
    r"^(#{1,4}\s+.+|Section\s+\d+[:.]?.+|ARTICLE\s+[IVXLCDM\d]+[:.]?.+)",
    re.MULTILINE | re.IGNORECASE,
)


def is_table_block(block: str) -> bool:
    """Check if block is a markdown table."""
    lines = [ln.strip() for ln in block.strip().split("\n") if ln.strip()]
    if len(lines) >= 2 and all(ln.startswith("|") and ln.endswith("|") for ln in lines):
        return True
    return False


def split_into_semantic_sections(text: str) -> list[tuple[str, str]]:
    """
    Split text into logical sections based on headers or double newlines.
    Returns a list of (section_title, section_body) tuples.
    """
    lines = text.split("\n")
    sections: list[tuple[str, list[str]]] = []
    current_title = "Overview"
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        header_match = _HEADER_PATTERN.match(stripped)
        if header_match:
            if current_lines:
                sections.append((current_title, current_lines))
                current_lines = []
            current_title = stripped.lstrip("#").strip()
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_title, current_lines))

    # Convert line arrays to blocks
    results: list[tuple[str, str]] = []
    for title, sec_lines in sections:
        body = "\n".join(sec_lines).strip()
        if body:
            results.append((title, body))

    return results


def chunk_document(
    title: str,
    text: str,
    category: str = "general",
    max_chunk_chars: int = 1500,
    min_chunk_chars: int = 15,
) -> list[dict[str, Any]]:
    """
    Section-aware chunker with table preservation and contextual prepending.
    Ensures markdown tables are never sliced in half.
    Prepends context metadata to each chunk.
    """
    sections = split_into_semantic_sections(text)
    chunks: list[dict[str, Any]] = []

    for sec_title, sec_body in sections:
        # Split section body by double newlines (paragraphs or table blocks)
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", sec_body) if p.strip()]

        current_chunk_paragraphs: list[str] = []
        current_len = 0

        for p in paragraphs:
            p_len = len(p)
            # If paragraph is a table, treat it with table guard (do not sever)
            if is_table_block(p):
                # If we have buffered text, flush it first so table stays unified
                if current_chunk_paragraphs:
                    chunk_text = "\n\n".join(current_chunk_paragraphs)
                    if len(chunk_text) >= min_chunk_chars:
                        chunks.append({"section_title": sec_title, "text": chunk_text})
                    current_chunk_paragraphs = []
                    current_len = 0
                chunks.append({"section_title": sec_title, "text": p})
                continue

            # Standard paragraph accumulation
            if current_len + p_len > max_chunk_chars and current_chunk_paragraphs:
                chunk_text = "\n\n".join(current_chunk_paragraphs)
                if len(chunk_text) >= min_chunk_chars:
                    chunks.append({"section_title": sec_title, "text": chunk_text})
                current_chunk_paragraphs = [p]
                current_len = p_len
            else:
                current_chunk_paragraphs.append(p)
                current_len += p_len + 2

        if current_chunk_paragraphs:
            chunk_text = "\n\n".join(current_chunk_paragraphs)
            if len(chunk_text) >= min_chunk_chars or not chunks:
                chunks.append({"section_title": sec_title, "text": chunk_text})

    # Fallback if no chunks generated
    if not chunks:
        chunks = [{"section_title": "Overview", "text": text.strip()}]

    # Apply contextual prepending and chunk indexing
    total_chunks = len(chunks)
    contextualized_chunks: list[dict[str, Any]] = []
    for idx, c in enumerate(chunks):
        sec_title = c["section_title"]
        body = c["text"]
        context_prefix = (
            f"[Bank: Meridian Trust & Savings Bank | Document: {title} | "
            f"Category: {category} | Section: {sec_title}]\n\n"
        )
        contextualized_chunks.append(
            {
                "chunk_index": idx,
                "total_chunks": total_chunks,
                "section_title": sec_title,
                "raw_text": body,
                "text": f"{context_prefix}{body}",
            }
        )

    return contextualized_chunks

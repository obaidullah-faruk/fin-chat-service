import base64
import logging
import os
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from knowledge.chunking import chunk_document
from knowledge.extractors import extract_document
from knowledge.store import get_knowledge_store
from security.auth import verify_internal_caller

logger = logging.getLogger("finchat.knowledge.routes")

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class IngestRequest(BaseModel):
    title: str | None = None
    filename: str
    category: str = "general"
    content_base64: str | None = None
    raw_text: str | None = None
    uploaded_by: str = "admin"
    collision_action: Literal["check", "replace", "alias", "force"] = "check"


class SearchRequest(BaseModel):
    query: str
    category: str | None = None
    top_k: int = 4


@router.get("/documents")
async def list_documents(_caller: str = Depends(verify_internal_caller)) -> list[dict[str, Any]]:
    """List all unique documents and metadata stored in Qdrant."""
    store = get_knowledge_store()
    return store.list_documents()


@router.post("/search")
async def search_knowledge(
    req: SearchRequest,
    _caller: str = Depends(verify_internal_caller),
) -> list[dict[str, Any]]:
    """Perform hybrid similarity search on the Qdrant knowledge base."""
    store = get_knowledge_store()
    return store.search_hybrid(query=req.query, category=req.category, top_k=req.top_k)


@router.post("/ingest")
async def ingest_document_route(
    req: IngestRequest,
    _caller: str = Depends(verify_internal_caller),
) -> dict[str, Any]:
    """Ingest a single document into Qdrant with content collision detection and FastEmbed."""
    store = get_knowledge_store()
    filename = req.filename
    category = req.category

    # Get raw bytes
    if req.content_base64:
        data = base64.b64decode(req.content_base64)
    elif req.raw_text:
        data = req.raw_text.encode("utf-8")
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either content_base64 or raw_text must be provided.",
        )

    # Extract text and compute hashes
    doc_info = extract_document(
        filename=filename,
        data=data,
        default_title=req.title,
        category=category,
    )
    title = doc_info["title"]
    text = doc_info["text"]
    raw_hash = doc_info["raw_file_hash"]
    content_hash = doc_info["content_hash"]
    file_format = doc_info["file_format"]

    doc_id = Path(filename).stem.lower().replace(" ", "_").replace("-", "_")

    # Check for content collision (different document but same content)
    existing = store.find_by_content_hash(content_hash)
    if existing and req.collision_action == "check":
        if existing.get("doc_id") != doc_id:
            return {
                "status": "collision",
                "message": (
                    f"Content collision detected! The extracted text is identical to existing document "
                    f"'{existing.get('title')}' ({existing.get('filename')}, v{existing.get('version')})."
                ),
                "existing_document": existing,
                "content_hash": content_hash,
            }

    # Version handling
    version = 1
    if existing and existing.get("doc_id") == doc_id:
        version = int(existing.get("version", 1))
        if req.collision_action == "replace":
            version += 1

    # Chunk the document
    chunks = chunk_document(title=title, text=text, category=category)

    # Ingest into Qdrant
    chunk_count = store.ingest_document_chunks(
        doc_id=doc_id,
        title=title,
        filename=filename,
        category=category,
        file_format=file_format,
        raw_file_hash=raw_hash,
        content_hash=content_hash,
        chunks=chunks,
        version=version,
        uploaded_by=req.uploaded_by,
    )

    return {
        "status": "success",
        "doc_id": doc_id,
        "title": title,
        "filename": filename,
        "category": category,
        "version": version,
        "chunk_count": chunk_count,
        "content_hash": content_hash,
    }


@router.delete("/documents/{doc_id}")
async def delete_document_route(
    doc_id: str,
    _caller: str = Depends(verify_internal_caller),
) -> dict[str, Any]:
    """Delete a document and all its vector chunks from Qdrant."""
    store = get_knowledge_store()
    success = store.delete_document(doc_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document {doc_id}",
        )
    return {"status": "success", "deleted_doc_id": doc_id}


@router.post("/seed-local")
async def seed_local_documents(
    _caller: str = Depends(verify_internal_caller),
) -> dict[str, Any]:
    """
    Scan the local data directory and index all bank documents into Qdrant.
    Deduplicates identical formats (prefers markdown or text if multiple formats exist).
    """
    store = get_knowledge_store()
    
    # Locate data directory in container or local environment
    candidates = [
        Path("/app/data"),
        Path("./data"),
        Path("../data"),
        Path("/Users/mdobaidullahalfaruk/Documents/fin-chat-service/data"),
    ]
    data_dir = None
    for c in candidates:
        if c.exists() and c.is_dir():
            data_dir = c
            break

    if not data_dir:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Local data directory not found for seeding.",
        )

    category_map = {
        "policies": "policy",
        "rates": "rates",
        "cards": "cards",
        "offers": "offers",
    }

    indexed_docs: list[str] = []
    total_chunks = 0
    seen_content_hashes: set[str] = set()

    # Prefer indexing .md or .txt files for clean semantic structure, while recording multi-format availability
    for subfolder, cat_name in category_map.items():
        folder_path = data_dir / subfolder
        if not folder_path.exists():
            continue

        # Group by stem (e.g. 'cd_ladder_rates')
        stem_groups: dict[str, list[Path]] = {}
        for file_path in folder_path.glob("*.*"):
            stem_groups.setdefault(file_path.stem, []).append(file_path)

        for stem, file_paths in stem_groups.items():
            # Pick best format to ingest: .md > .txt > .pdf > .docx > .json
            format_priority = [".md", ".txt", ".pdf", ".docx", ".json"]
            best_file = sorted(
                file_paths,
                key=lambda p: format_priority.index(p.suffix.lower())
                if p.suffix.lower() in format_priority
                else 99,
            )[0]

            with open(best_file, "rb") as f:
                data = f.read()

            doc_info = extract_document(
                filename=best_file.name,
                data=data,
                category=cat_name,
            )

            content_hash = doc_info["content_hash"]
            if content_hash in seen_content_hashes:
                logger.info("Skipping exact duplicate content hash during seeding: %s", best_file.name)
                continue
            seen_content_hashes.add(content_hash)

            doc_id = stem.lower().replace("-", "_")
            chunks = chunk_document(
                title=doc_info["title"],
                text=doc_info["text"],
                category=cat_name,
            )

            cnt = store.ingest_document_chunks(
                doc_id=doc_id,
                title=doc_info["title"],
                filename=best_file.name,
                category=cat_name,
                file_format=doc_info["file_format"],
                raw_file_hash=doc_info["raw_file_hash"],
                content_hash=content_hash,
                chunks=chunks,
                version=1,
                uploaded_by="system_seeder",
            )
            indexed_docs.append(doc_id)
            total_chunks += cnt

    return {
        "status": "success",
        "indexed_documents_count": len(indexed_docs),
        "total_chunks_indexed": total_chunks,
        "documents": indexed_docs,
    }

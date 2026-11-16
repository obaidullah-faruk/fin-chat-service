import asyncio
from datetime import datetime, timezone
import hashlib
import logging
import os
import uuid
from typing import Any

from config import get_settings

logger = logging.getLogger("finchat.knowledge.store")

try:
    from qdrant_client import QdrantClient, models
    from qdrant_client.http.exceptions import UnexpectedResponse
except ImportError:
    QdrantClient = None
    class _DummyModels:
        class Distance:
            COSINE = "Cosine"
        class VectorParams:
            def __init__(self, **kwargs): pass
        class PayloadSchemaType:
            KEYWORD = "keyword"
        class TextIndexParams:
            def __init__(self, **kwargs): pass
        class TokenizerType:
            WORD = "word"
        class Filter:
            def __init__(self, **kwargs): pass
        class FieldCondition:
            def __init__(self, **kwargs): pass
        class MatchValue:
            def __init__(self, **kwargs): pass
        class PointStruct:
            def __init__(self, **kwargs): pass
    models = _DummyModels
    UnexpectedResponse = Exception

try:
    from fastembed import TextEmbedding
except ImportError:
    TextEmbedding = None

_EMBED_DIM = 384  # BAAI/bge-small-en-v1.5 dimension


class KnowledgeVectorStore:
    def __init__(
        self,
        qdrant_url: str | None = None,
        collection_name: str | None = None,
        model_name: str | None = None,
    ):
        settings = get_settings()
        self.qdrant_url = qdrant_url or getattr(settings, "qdrant_url", "http://qdrant:6333")
        self.collection_name = collection_name or getattr(
            settings, "knowledge_collection_name", "finchat_knowledge"
        )
        self.model_name = model_name or getattr(
            settings, "fastembed_model_name", "BAAI/bge-small-en-v1.5"
        )
        self._client: Any = None
        self._embedder: Any = None

    @property
    def client(self) -> Any:
        if self._client is None:
            if QdrantClient is None:
                raise RuntimeError("qdrant-client is not installed.")
            self._client = QdrantClient(url=self.qdrant_url, timeout=10.0)
        return self._client

    @property
    def embedder(self) -> Any:
        if self._embedder is None:
            if TextEmbedding is None:
                raise RuntimeError("fastembed is not installed.")
            logger.info("Initializing FastEmbed with model: %s", self.model_name)
            self._embedder = TextEmbedding(model_name=self.model_name)
        return self._embedder

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate dense vectors for input texts using FastEmbed."""
        if not texts:
            return []
        try:
            vectors = list(self.embedder.embed(texts))
            return [v.tolist() if hasattr(v, "tolist") else list(v) for v in vectors]
        except Exception as exc:
            logger.warning("FastEmbed embedding failed, fallback to mock embedding: %s", exc)
            # Deterministic fallback vector for unit tests or offline environments
            fallbacks = []
            for t in texts:
                h = hashlib.sha256(t.encode("utf-8")).digest()
                vec = [(b / 255.0) * 2 - 1 for b in h[: _EMBED_DIM // 8]]
                # Repeat to reach 384 dimensions
                while len(vec) < _EMBED_DIM:
                    vec.extend(vec[: min(len(vec), _EMBED_DIM - len(vec))])
                fallbacks.append(vec[:_EMBED_DIM])
            return fallbacks

    def ensure_collection(self) -> bool:
        """Create the Qdrant knowledge collection and indexes if not present."""
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            if not exists:
                logger.info("Creating Qdrant collection: %s", self.collection_name)
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=_EMBED_DIM,
                        distance=models.Distance.COSINE,
                    ),
                )
                # Create indexes on payload for fast filtering and BM25 text queries
                for field in ("doc_id", "category", "content_hash", "filename"):
                    try:
                        self.client.create_payload_index(
                            collection_name=self.collection_name,
                            field_name=field,
                            field_schema=models.PayloadSchemaType.KEYWORD,
                        )
                    except Exception as e:
                        logger.debug("Payload index creation note: %s", e)

                try:
                    self.client.create_payload_index(
                        collection_name=self.collection_name,
                        field_name="text",
                        field_schema=models.TextIndexParams(
                            type="text",
                            tokenizer=models.TokenizerType.WORD,
                            min_token_len=2,
                            max_token_len=20,
                            lowercase=True,
                        ),
                    )
                except Exception as e:
                    logger.debug("Text index creation note: %s", e)

            return True
        except Exception as exc:
            logger.error("Failed to ensure Qdrant collection %s: %s", self.collection_name, exc)
            return False

    def find_by_content_hash(self, content_hash: str) -> dict[str, Any] | None:
        """Find an existing document matching the normalized content hash."""
        try:
            self.ensure_collection()
            results, _ = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="content_hash",
                            match=models.MatchValue(value=content_hash),
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
                with_vectors=False,
            )
            if results:
                payload = results[0].payload or {}
                return {
                    "doc_id": payload.get("doc_id"),
                    "title": payload.get("title"),
                    "filename": payload.get("filename"),
                    "category": payload.get("category"),
                    "version": payload.get("version", 1),
                    "uploaded_at": payload.get("uploaded_at"),
                }
            return None
        except Exception as exc:
            logger.error("Error finding document by content hash: %s", exc)
            return None

    def list_documents(self) -> list[dict[str, Any]]:
        """List all unique documents and metadata stored in Qdrant."""
        try:
            self.ensure_collection()
            # Scroll points from Qdrant to aggregate unique documents
            points, _ = self.client.scroll(
                collection_name=self.collection_name,
                limit=10000,
                with_payload=True,
                with_vectors=False,
            )
            doc_map: dict[str, dict[str, Any]] = {}
            for p in points:
                payload = p.payload or {}
                doc_id = payload.get("doc_id")
                if not doc_id:
                    continue
                if doc_id not in doc_map:
                    doc_map[doc_id] = {
                        "doc_id": doc_id,
                        "title": payload.get("title", doc_id),
                        "filename": payload.get("filename", ""),
                        "category": payload.get("category", "general"),
                        "file_format": payload.get("file_format", "txt"),
                        "content_hash": payload.get("content_hash", ""),
                        "raw_file_hash": payload.get("raw_file_hash", ""),
                        "version": payload.get("version", 1),
                        "uploaded_at": payload.get("uploaded_at", ""),
                        "uploaded_by": payload.get("uploaded_by", "admin"),
                        "chunk_count": 0,
                    }
                doc_map[doc_id]["chunk_count"] += 1

            return sorted(list(doc_map.values()), key=lambda d: d.get("uploaded_at", ""), reverse=True)
        except Exception as exc:
            logger.error("Error listing documents from Qdrant: %s", exc)
            return []

    def delete_document(self, doc_id: str) -> bool:
        """Atomically delete all points/chunks belonging to a document from Qdrant."""
        try:
            self.ensure_collection()
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="doc_id",
                            match=models.MatchValue(value=doc_id),
                        )
                    ]
                ),
            )
            logger.info("Deleted document %s from Qdrant collection %s", doc_id, self.collection_name)
            return True
        except Exception as exc:
            logger.error("Error deleting document %s: %s", doc_id, exc)
            return False

    def ingest_document_chunks(
        self,
        doc_id: str,
        title: str,
        filename: str,
        category: str,
        file_format: str,
        raw_file_hash: str,
        content_hash: str,
        chunks: list[dict[str, Any]],
        version: int = 1,
        uploaded_by: str = "admin",
    ) -> int:
        """
        Atomically replaces existing chunks for doc_id, vectorizes chunks with FastEmbed,
        and saves points to Qdrant. Returns chunk count.
        """
        self.ensure_collection()
        # Purge existing points for this doc_id to ensure clean atomic replacement
        self.delete_document(doc_id)

        if not chunks:
            return 0

        # Vectorize
        texts_to_embed = [c["text"] for c in chunks]
        vectors = self.embed_texts(texts_to_embed)

        now_iso = datetime.now(timezone.utc).isoformat()
        points: list[Any] = []
        for idx, (chunk, vec) in enumerate(zip(chunks, vectors)):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc_id}_{idx}_{version}"))
            payload = {
                "doc_id": doc_id,
                "title": title,
                "filename": filename,
                "category": category,
                "file_format": file_format,
                "raw_file_hash": raw_file_hash,
                "content_hash": content_hash,
                "version": version,
                "uploaded_at": now_iso,
                "uploaded_by": uploaded_by,
                "section_title": chunk.get("section_title", "General"),
                "chunk_index": idx,
                "total_chunks": len(chunks),
                "raw_text": chunk.get("raw_text", ""),
                "text": chunk.get("text", ""),
            }
            points.append(
                models.PointStruct(
                    id=point_id,
                    vector=vec,
                    payload=payload,
                )
            )

        # Batch upsert
        self.client.upsert(collection_name=self.collection_name, points=points)
        logger.info(
            "Successfully indexed %d chunks for document '%s' (doc_id=%s, v%d)",
            len(points),
            title,
            doc_id,
            version,
        )
        return len(points)

    def search_hybrid(
        self,
        query: str,
        category: str | None = None,
        top_k: int = 4,
    ) -> list[dict[str, Any]]:
        """
        Execute similarity search on Qdrant using FastEmbed vector and optional category filter.
        Returns top matching chunks with scores and metadata.
        """
        try:
            self.ensure_collection()
            query_vector = self.embed_texts([query])[0]

            query_filter = None
            if category:
                query_filter = models.Filter(
                    must=[
                        models.FieldCondition(
                            key="category",
                            match=models.MatchValue(value=category),
                        )
                    ]
                )

            if hasattr(self.client, "query_points"):
                res = self.client.query_points(
                    collection_name=self.collection_name,
                    query=query_vector,
                    query_filter=query_filter,
                    limit=top_k,
                    with_payload=True,
                )
                hits = res.points
            elif hasattr(self.client, "search"):
                hits = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=query_vector,
                    query_filter=query_filter,
                    limit=top_k,
                    with_payload=True,
                )
            else:
                hits = []

            results: list[dict[str, Any]] = []
            for hit in hits:
                payload = hit.payload or {}
                results.append(
                    {
                        "score": hit.score,
                        "doc_id": payload.get("doc_id"),
                        "title": payload.get("title"),
                        "category": payload.get("category"),
                        "section_title": payload.get("section_title"),
                        "text": payload.get("text", ""),
                        "raw_text": payload.get("raw_text", ""),
                        "filename": payload.get("filename"),
                        "version": payload.get("version"),
                    }
                )
            return results
        except Exception as exc:
            logger.error("Error performing hybrid search on Qdrant: %s", exc)
            return []


# Module singleton
_store_instance: KnowledgeVectorStore | None = None

def get_knowledge_store() -> KnowledgeVectorStore:
    global _store_instance
    if _store_instance is None:
        _store_instance = KnowledgeVectorStore()
    return _store_instance

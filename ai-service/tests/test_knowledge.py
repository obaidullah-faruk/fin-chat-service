import json
from unittest.mock import MagicMock, patch
import pytest

from knowledge.chunking import chunk_document, is_table_block, split_into_semantic_sections
from knowledge.extractors import (
    compute_content_hash,
    compute_raw_hash,
    extract_document,
    normalize_text_for_hashing,
)
from knowledge.store import KnowledgeVectorStore


def test_normalize_and_content_hash():
    text1 = "  Meridian Trust & Savings   Bank \n\nPolicy   Document.  "
    text2 = "meridian trust & savings bank policy document."
    
    assert normalize_text_for_hashing(text1) == normalize_text_for_hashing(text2)
    assert compute_content_hash(text1) == compute_content_hash(text2)

    text3 = "Different banking text"
    assert compute_content_hash(text1) != compute_content_hash(text3)


def test_extract_markdown_document():
    raw_md = b"# Overdraft Privilege Policy\n\nSection 1: Fees\nThe fee is $35 per item."
    doc = extract_document("overdraft_policy.md", raw_md, category="policy")

    assert doc["title"] == "Overdraft Privilege Policy"
    assert doc["category"] == "policy"
    assert doc["file_format"] == "md"
    assert "fee is $35" in doc["text"]
    assert len(doc["content_hash"]) == 64
    assert len(doc["raw_file_hash"]) == 64


def test_extract_json_document():
    data = {
        "title": "5.35% Promotional CD",
        "category": "offers",
        "content": "Special promotional 9-month CD paying 5.35% APY.",
        "metadata": {"min_deposit": 10000},
    }
    raw_json = json.dumps(data).encode("utf-8")
    doc = extract_document("special_cd.json", raw_json, category="offers")

    assert doc["title"] == "5.35% Promotional CD"
    assert doc["category"] == "offers"
    assert "5.35% APY" in doc["text"]
    assert doc["metadata"].get("min_deposit") == 10000


def test_is_table_block():
    table = "| Term | Rate | APY |\n| --- | --- | --- |\n| 12 Mo | 4.5% | 4.6% |"
    non_table = "This is just a regular sentence about banking."
    
    assert is_table_block(table) is True
    assert is_table_block(non_table) is False


def test_chunking_with_table_preservation_and_context_prefix():
    text = (
        "# Certificate of Deposit (CD) Ladder Rates\n\n"
        "## Section 1: Standard CD Rates\n"
        "Here are our fixed deposit term rates:\n\n"
        "| Term | Interest Rate | Annual Percentage Yield (APY) |\n"
        "| --- | --- | --- |\n"
        "| 3 Months | 3.20% | 3.25% |\n"
        "| 6 Months | 4.10% | 4.18% |\n"
        "| 12 Months | 4.65% | 4.75% |\n"
        "| 24 Months | 4.40% | 4.50% |\n\n"
        "## Section 2: Early Withdrawal Penalties\n"
        "Early withdrawal of principal incurs a penalty of 90 days simple interest."
    )

    chunks = chunk_document(
        title="CD Ladder Rates",
        text=text,
        category="rates",
    )

    assert len(chunks) >= 2
    # Verify context prefix exists on all chunks
    for c in chunks:
        assert "[Bank: Meridian Trust & Savings Bank | Document: CD Ladder Rates" in c["text"]
        assert "Category: rates" in c["text"]

    # Verify table is preserved as a cohesive block
    table_chunk = next((c for c in chunks if "| 3 Months |" in c["text"]), None)
    assert table_chunk is not None
    assert "| 24 Months |" in table_chunk["text"]
    assert "| Term | Interest Rate |" in table_chunk["text"]


def test_vector_store_mocked_qdrant():
    store = KnowledgeVectorStore(qdrant_url="http://mock-qdrant:6333")
    mock_client = MagicMock()
    store._client = mock_client
    
    # Mock collection check
    mock_collection = MagicMock()
    mock_collection.name = "finchat_knowledge"
    mock_client.get_collections.return_value.collections = [mock_collection]

    # Test collection ensure
    assert store.ensure_collection() is True

    # Test find_by_content_hash with mock
    mock_point = MagicMock()
    mock_point.payload = {
        "doc_id": "test_doc",
        "title": "Test Title",
        "filename": "test.txt",
        "category": "rates",
        "version": 1,
    }
    mock_client.scroll.return_value = ([mock_point], None)

    existing = store.find_by_content_hash("mockhash123")
    assert existing is not None
    assert existing["doc_id"] == "test_doc"

    # Test delete document
    assert store.delete_document("test_doc") is True
    mock_client.delete.assert_called_once()

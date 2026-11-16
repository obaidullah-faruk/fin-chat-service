import logging
from typing import Any

from langchain_core.tools import tool

from knowledge.store import get_knowledge_store

logger = logging.getLogger("finchat.knowledge.tools")


@tool
def search_bank_knowledge(query: str, category: str | None = None) -> str:
    """
    Search Meridian Trust & Savings Bank (MTSB) knowledge base for official policies,
    interest rate schedules, loan terms, credit/debit card agreements, and promotional offers.
    
    Args:
        query: Specific banking search query (e.g. "9-month CD interest rate", "overdraft fee policy",
               "credit card cash rewards tiers", "welcome checking bonus").
        category: Optional category filter: 'policy', 'rates', 'cards', 'offers', or 'general'.
    """
    store = get_knowledge_store()
    results = store.search_hybrid(query=query, category=category, top_k=4)

    if not results:
        return (
            f"No specific banking documentation found in the knowledge base for query: '{query}'. "
            "Please check the query terms or ask about bank policies, interest rates, cards, or offers."
        )

    formatted = [f"Found {len(results)} relevant official banking knowledge document passage(s):\n"]
    for idx, r in enumerate(results, 1):
        doc_title = r.get("title", "Bank Document")
        sec_title = r.get("section_title", "General")
        cat = r.get("category", "General")
        filename = r.get("filename", "")
        raw_text = r.get("raw_text") or r.get("text", "")
        formatted.append(
            f"--- [Passage {idx} | Document: {doc_title} | Section: {sec_title} | Category: {cat} | Source File: {filename}] ---\n"
            f"{raw_text}\n"
        )

    return "\n".join(formatted)

"""Keyword and indication-tag retrieval. No embeddings and no network."""

from __future__ import annotations

import re

from src.config import FALLBACK_MESSAGE
from src.models import Catalog, RetrievalResult, RetrievedDoc

_STOP = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "are",
    "was",
    "were",
    "you",
    "your",
    "can",
    "what",
    "how",
    "who",
    "why",
    "when",
}


def retrieve_content(
    catalog: Catalog,
    *,
    indication: str,
    query: str,
    top_k: int = 5,
) -> RetrievalResult:
    """Return approved documents tagged for the indication, best match first.

    An empty result is a hard failure. Callers must withhold recommendations
    instead of filling the gap with uncited text.
    """
    if not catalog.documents:
        return RetrievalResult(
            ok=False,
            indication=indication,
            query=query,
            fallback_reason=FALLBACK_MESSAGE,
        )

    query_tokens = _tokens(query)
    ranked: list[RetrievedDoc] = []
    for document in catalog.documents:
        if indication not in document.indication_tags:
            continue
        doc_tokens = _tokens(f"{document.title} {document.body}")
        overlap = 0.0
        if query_tokens:
            overlap = len(query_tokens & doc_tokens) / len(query_tokens)
        score = round(0.6 + 0.4 * overlap, 4)
        ranked.append(RetrievedDoc(document=document, score=score))

    ranked.sort(key=lambda item: (-item.score, item.document.content_id))
    chosen = ranked[:top_k]
    if not chosen:
        return RetrievalResult(
            ok=False,
            indication=indication,
            query=query,
            fallback_reason=FALLBACK_MESSAGE,
        )
    return RetrievalResult(ok=True, indication=indication, query=query, docs=chosen)


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in _STOP
    }

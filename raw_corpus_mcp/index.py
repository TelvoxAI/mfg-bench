"""Keyword (BM25) and hybrid (BM25 + embeddings, reciprocal rank fusion) retrieval over
the corpus (IND-982 Part I).

Both arms share this code; the only difference between `claude-raw` and
`claude-semantic` is which `search` the server exposes. The vector side is optional at
load time: with no embedding file the hybrid index degrades to BM25 and says so.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import date

import numpy as np
from rank_bm25 import BM25Okapi

from raw_corpus_mcp.corpus import Doc, tokenize

Embedder = Callable[[list[str]], np.ndarray]  # texts → (n, dim) unit vectors


class Filters:
    def __init__(self, sources: list[str] | None = None, date_from: str = "", date_to: str = "",
                 sender: str = ""):
        self.sources = {s.strip().lower() for s in (sources or []) if s.strip()}
        self.date_from = date.fromisoformat(date_from[:10]) if date_from else None
        self.date_to = date.fromisoformat(date_to[:10]) if date_to else None
        self.sender = sender.strip().lower()

    def allows(self, d: Doc) -> bool:
        if self.sources and d.source not in self.sources:
            return False
        if self.date_from and (d.date is None or d.date < self.date_from):
            return False
        if self.date_to and (d.date is None or d.date > self.date_to):
            return False
        if self.sender:
            hay = " ".join([d.author, *d.participants]).lower()
            if self.sender not in hay:
                return False
        return True


class KeywordIndex:
    def __init__(self, docs: list[Doc]):
        self.docs = docs
        self.by_id = {d.doc_id: d for d in docs}
        self.bm25 = BM25Okapi([d.tokens for d in docs]) if docs else None

    def scores(self, query: str) -> np.ndarray:
        if self.bm25 is None:
            return np.zeros(0)
        return np.asarray(self.bm25.get_scores(tokenize(query)), dtype=np.float32)

    def search(self, query: str, k: int, filters: Filters) -> list[tuple[Doc, float]]:
        s = self.scores(query)
        order = np.argsort(-s)
        out = []
        for i in order:
            if s[i] <= 0:
                break
            d = self.docs[int(i)]
            if filters.allows(d):
                out.append((d, float(s[i])))
                if len(out) >= k:
                    break
        return out


class VectorStore:
    """Unit-normalised embeddings aligned with a doc-id list, saved as `.npy` + `.json`."""

    def __init__(self, ids: list[str], matrix: np.ndarray):
        self.ids = ids
        self.pos = {i: n for n, i in enumerate(ids)}
        self.matrix = matrix.astype(np.float32)
        norms = np.linalg.norm(self.matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self.matrix /= norms

    @classmethod
    def load(cls, path_stem: str) -> VectorStore | None:
        npy, ids = f"{path_stem}.npy", f"{path_stem}.json"
        if not (os.path.exists(npy) and os.path.exists(ids)):
            return None
        with open(ids) as f:
            return cls(json.load(f), np.load(npy))

    def save(self, path_stem: str) -> None:
        np.save(f"{path_stem}.npy", self.matrix)
        with open(f"{path_stem}.json", "w") as f:
            json.dump(self.ids, f)

    def scores(self, qvec: np.ndarray) -> np.ndarray:
        q = qvec.astype(np.float32).reshape(-1)
        n = np.linalg.norm(q) or 1.0
        return self.matrix @ (q / n)


def rrf(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    """Reciprocal rank fusion of several ranked id lists."""
    fused: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (k + rank)
    return fused


class HybridIndex:
    def __init__(self, docs: list[Doc], vectors: VectorStore | None, embed: Embedder | None,
                 candidates: int = 200):
        self.keyword = KeywordIndex(docs)
        self.docs = docs
        self.by_id = self.keyword.by_id
        self.vectors = vectors
        self.embed = embed
        self.candidates = candidates

    @property
    def has_vectors(self) -> bool:
        return self.vectors is not None and self.embed is not None

    def search(self, query: str, k: int, filters: Filters) -> list[tuple[Doc, float]]:
        # BM25 ranking over the filtered corpus
        s = self.keyword.scores(query)
        allowed = [i for i, d in enumerate(self.docs) if filters.allows(d)]
        if not allowed:
            return []
        bm_order = sorted(allowed, key=lambda i: -s[i])
        bm_rank = [self.docs[i].doc_id for i in bm_order[: self.candidates] if s[i] > 0]
        rankings = [bm_rank]
        if self.has_vectors:
            qv = self.embed([query])[0]
            v = self.vectors.scores(qv)
            vec_scores = []
            for i in allowed:
                p = self.vectors.pos.get(self.docs[i].doc_id)
                if p is not None:
                    vec_scores.append((float(v[p]), self.docs[i].doc_id))
            vec_scores.sort(reverse=True)
            rankings.append([d for _, d in vec_scores[: self.candidates]])
        fused = rrf(rankings)
        top = sorted(fused.items(), key=lambda kv: -kv[1])[:k]
        return [(self.by_id[d], score) for d, score in top]

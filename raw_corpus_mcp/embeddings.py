"""Embeddings for the hybrid arm (IND-982 Part I).

One strong current model, named in the report, not tuned on the test split. Vectors for
the corpus are built once (`python -m raw_corpus_mcp.build_vectors`) and shipped next to
the corpus; queries are embedded at request time with the same model.
"""

from __future__ import annotations

import os

import numpy as np

from raw_corpus_mcp.index import Embedder


def openai_embedder(model: str = "text-embedding-3-large", batch: int = 128) -> Embedder:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY"))

    def embed(texts: list[str]) -> np.ndarray:
        out: list[list[float]] = []
        for i in range(0, len(texts), batch):
            chunk = [t[:8000] for t in texts[i:i + batch]]
            resp = client.embeddings.create(model=model, input=chunk)
            out.extend(d.embedding for d in sorted(resp.data, key=lambda d: d.index))
        return np.asarray(out, dtype=np.float32)

    return embed

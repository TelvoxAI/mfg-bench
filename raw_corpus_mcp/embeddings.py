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


def bedrock_embedder(model: str = "amazon.titan-embed-text-v2:0", dims: int = 1024) -> Embedder:
    """Amazon Titan Text Embeddings v2 on Bedrock (bearer key from AWS_BEARER_TOKEN_BEDROCK).
    One text per call; 1024 normalised dimensions."""
    import json

    import boto3

    try:  # the bearer key lives in .env when run from the repo
        from dotenv import load_dotenv

        load_dotenv(override=False)
    except ImportError:
        pass
    client = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))

    def embed(texts: list[str]) -> np.ndarray:
        out = []
        for t in texts:
            body = json.dumps({"inputText": t[:8000], "dimensions": dims, "normalize": True})
            r = client.invoke_model(modelId=model, body=body, contentType="application/json", accept="application/json")
            out.append(json.loads(r["body"].read())["embedding"])
        return np.asarray(out, dtype=np.float32)

    return embed


def embedder_for(model: str) -> Embedder:
    """Pick the client by model id: `amazon.`/`cohere.` → Bedrock, else OpenAI."""
    if model.startswith(("amazon.", "cohere.")):
        return bedrock_embedder(model)
    return openai_embedder(model)


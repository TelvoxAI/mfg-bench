"""Embed the corpus once for the hybrid arm.

    python -m raw_corpus_mcp.build_vectors --corpus generated_data/sources --out gold/vectors \\
        [--model text-embedding-3-large] [--limit N]

Writes <out>.npy (unit vectors) and <out>.json (doc ids, same order). Resumable: an
existing pair is loaded and only missing documents are embedded.
"""

from __future__ import annotations

import argparse
import json
import os

import numpy as np

from raw_corpus_mcp.corpus import load_corpus
from raw_corpus_mcp.embeddings import embedder_for
from raw_corpus_mcp.index import VectorStore


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="generated_data/sources")
    ap.add_argument("--out", default="gold/vectors")
    ap.add_argument("--model", default="amazon.titan-embed-text-v2:0")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    docs = load_corpus(args.corpus)
    if args.limit:
        docs = docs[: args.limit]
    existing = VectorStore.load(args.out)
    ids, rows = (list(existing.ids), [existing.matrix]) if existing else ([], [])
    have = set(ids)
    todo = [d for d in docs if d.doc_id not in have]
    print(f"{len(docs)} docs, {len(have)} already embedded, {len(todo)} to embed with {args.model}")
    if todo:
        embed = embedder_for(args.model)
        B = 64
        for i in range(0, len(todo), B):
            chunk = todo[i:i + B]
            rows.append(embed([d.text for d in chunk]))
            ids.extend(d.doc_id for d in chunk)
            VectorStore(ids, np.vstack(rows)).save(args.out)
            print(f"  {min(i + B, len(todo))}/{len(todo)} saved")
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(f"{args.out}.meta.json", "w") as f:
        json.dump({"model": args.model, "docs": len(ids)}, f)
    print("done:", f"{args.out}.npy", f"{args.out}.json")


if __name__ == "__main__":
    main()

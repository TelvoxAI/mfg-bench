"""raw-corpus-mcp — the retrieval baselines of IND-982 Part I as one MCP server.

Two modes, one codebase, so the only difference between the `claude-raw` and
`claude-semantic` arms is the retrieval method:

* `MODE=keyword` (claude-raw, "connect your apps to Claude"): per-source keyword search
  with filters — `search(source, query, k, date_from, date_to, sender)`, `read(doc_id)`,
  `list(source, path)`.
* `MODE=hybrid` (claude-semantic, "well-built RAG"): one hybrid index across every
  source — `search(query, k, sources, date_from, date_to)` (BM25 + embeddings fused by
  reciprocal rank) and `read(doc_id)`.

Transport: streamable HTTP at `/mcp`, stateless, JSON responses, behind a bearer token
(`MCP_AUTH_TOKEN`) — what the Claude Messages API MCP connector needs
(`mcp_servers=[{"type": "url", "url": ..., "authorization_token": ...}]`).

Environment:
    MODE=keyword|hybrid       CORPUS_DIR=/data/sources      MCP_AUTH_TOKEN=...
    VECTORS=/data/vectors     (hybrid: stem of <stem>.npy + <stem>.json from build_vectors)
    EMBED_MODEL=text-embedding-3-large   LLM_API_KEY / OPENAI_API_KEY (hybrid queries)
    PORT=8080
"""

from __future__ import annotations

import logging
import os
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from raw_corpus_mcp.corpus import SOURCES, Doc, load_corpus, tokenize
from raw_corpus_mcp.index import Filters, HybridIndex, KeywordIndex, VectorStore

logger = logging.getLogger("raw_corpus_mcp")

MODE = os.environ.get("MODE", "keyword").lower()
CORPUS_DIR = os.environ.get("CORPUS_DIR", "generated_data/sources")
MAX_K = 25
MAX_READ_CHARS = int(os.environ.get("MAX_READ_CHARS", "20000"))


class State:
    docs: list[Doc] = []
    keyword: KeywordIndex | None = None
    hybrid: HybridIndex | None = None
    by_id: dict[str, Doc] = {}


def _hit(d: Doc, score: float, query: str) -> dict[str, Any]:
    return {"doc_id": d.doc_id, "source": d.source, "path": d.path, "title": d.title,
            "date": d.date_str, "author": d.author, "score": round(score, 4),
            "snippet": d.snippet(set(tokenize(query)))}


def load(corpus_dir: str = CORPUS_DIR, mode: str = MODE) -> None:
    State.docs = load_corpus(corpus_dir)
    State.by_id = {d.doc_id: d for d in State.docs}
    if mode == "hybrid":
        vectors = VectorStore.load(os.environ["VECTORS"]) if os.environ.get("VECTORS") else None
        embed = None
        if vectors is not None:
            from raw_corpus_mcp.embeddings import embedder_for

            embed = embedder_for(os.environ.get("EMBED_MODEL", "amazon.titan-embed-text-v2:0"))
        State.hybrid = HybridIndex(State.docs, vectors, embed)
        State.keyword = State.hybrid.keyword
        logger.info("hybrid index: %d docs, vectors=%s", len(State.docs), vectors is not None)
    else:
        State.keyword = KeywordIndex(State.docs)
        logger.info("keyword index: %d docs", len(State.docs))


def build_server(mode: str = MODE) -> MCPServer:
    name = "raw-corpus-keyword" if mode == "keyword" else "raw-corpus-hybrid"
    server = MCPServer(
        name,
        instructions=(
            "Search and read the company's documents. Sources: " + ", ".join(SOURCES) + ". "
            "Document ids look like dsid_…; cite them in your answer."
        ),
    )

    if mode == "keyword":

        @server.tool(description=(
            "Keyword search inside ONE source (outlook, teams, sharepoint, hubspot, erp, quality). "
            "Matches words and ids in title and text; optional date range (YYYY-MM-DD) and a "
            "sender/participant substring. Returns up to k hits with a snippet."))
        def search(source: str, query: str, k: int = 10, date_from: str = "", date_to: str = "",
                   sender: str = "") -> dict[str, Any]:
            src = source.strip().lower()
            if src not in SOURCES:
                return {"error": f"unknown source {source!r}; use one of {list(SOURCES)}"}
            f = Filters(sources=[src], date_from=date_from, date_to=date_to, sender=sender)
            hits = State.keyword.search(query, max(1, min(int(k), MAX_K)), f)
            return {"source": src, "query": query, "hits": [_hit(d, s, query) for d, s in hits]}

        @server.tool(name="list", description=(
            "List the folders and documents under a path of a source, like a file browser "
            "(e.g. source='outlook', path='laura.kim'). Returns child folders and up to 100 "
            "documents with their ids and dates."))
        def list_docs(source: str, path: str = "", limit: int = 100) -> dict[str, Any]:
            src = source.strip().lower()
            if src not in SOURCES:
                return {"error": f"unknown source {source!r}; use one of {list_sources()}"}
            prefix = f"{src}/" + (path.strip("/") + "/" if path.strip("/") else "")
            folders: set[str] = set()
            docs = []
            for d in State.docs:
                if not d.path.startswith(prefix):
                    continue
                rest = d.path[len(prefix):]
                if "/" in rest:
                    folders.add(rest.split("/", 1)[0])
                else:
                    docs.append({"doc_id": d.doc_id, "path": d.path, "title": d.title, "date": d.date_str})
            docs.sort(key=lambda x: (x["date"], x["path"]))
            return {"source": src, "path": path, "folders": sorted(folders),
                    "documents": docs[: max(1, min(int(limit), 500))], "total_documents": len(docs)}

    else:

        @server.tool(description=(
            "Semantic + keyword search across ALL sources (one hybrid index). Optional "
            "filters: sources (list of outlook, teams, sharepoint, hubspot, erp, quality) "
            "and a date range (YYYY-MM-DD). Returns up to k hits with a snippet."))
        def search(query: str, k: int = 10, sources: list[str] | None = None, date_from: str = "",
                   date_to: str = "") -> dict[str, Any]:
            bad = [s for s in (sources or []) if s.strip().lower() not in SOURCES]
            if bad:
                return {"error": f"unknown sources {bad}; use {list(SOURCES)}"}
            f = Filters(sources=sources, date_from=date_from, date_to=date_to)
            hits = State.hybrid.search(query, max(1, min(int(k), MAX_K)), f)
            return {"query": query, "vectors": State.hybrid.has_vectors,
                    "hits": [_hit(d, s, query) for d, s in hits]}

    @server.tool(description="Read one document in full by its doc_id (dsid_…).")
    def read(doc_id: str) -> dict[str, Any]:
        d = State.by_id.get(doc_id.strip())
        if d is None:
            return {"error": f"no document {doc_id!r}"}
        text = d.text
        truncated = len(text) > MAX_READ_CHARS
        return {"doc_id": d.doc_id, "source": d.source, "path": d.path, "title": d.title,
                "date": d.date_str, "author": d.author, "participants": d.participants,
                "text": text[:MAX_READ_CHARS], "truncated": truncated}

    return server


def list_sources() -> list[str]:
    return list(SOURCES)


class BearerAuth(BaseHTTPMiddleware):
    """Every request must carry `Authorization: Bearer <MCP_AUTH_TOKEN>`; `/healthz` is open."""

    def __init__(self, app, token: str):
        super().__init__(app)
        self.token = token

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/healthz":
            return JSONResponse({"ok": True, "mode": MODE, "docs": len(State.docs)})
        auth = request.headers.get("authorization", "")
        if not self.token or auth != f"Bearer {self.token}":
            return Response("unauthorized", status_code=401)
        return await call_next(request)


def build_app(mode: str = MODE, token: str | None = None):
    server = build_server(mode)
    app = server.streamable_http_app(
        json_response=True, stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    token = token if token is not None else os.environ.get("MCP_AUTH_TOKEN", "")
    if not token:
        raise RuntimeError("MCP_AUTH_TOKEN is required: the server must not be open")
    return BearerAuth(app, token)


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    load()
    uvicorn.run(build_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))


if __name__ == "__main__":
    main()

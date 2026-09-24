"""raw-corpus-mcp: corpus loading, keyword search with filters, hybrid fusion, and the
tools as the MCP client sees them. Run: `pytest raw_corpus_mcp -q`."""

from __future__ import annotations

import asyncio
import json

import numpy as np
import pytest

from raw_corpus_mcp import server as srv
from raw_corpus_mcp.corpus import load_corpus, tokenize
from raw_corpus_mcp.index import Filters, HybridIndex, KeywordIndex, VectorStore, rrf


def _write(root, rel, doc):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc))


@pytest.fixture
def corpus(tmp_path):
    _write(tmp_path, "outlook/laura.kim/2026-03-04-po.json", {
        "subject": "Re: PO 44817 promised date", "from": "Ana Ruiz <ana.ruiz@precisionmach.com>",
        "to": ["laura.kim@brightwaterpkg.com"], "cc": [], "sent_at": "2026-03-04T09:12", "mailbox": "laura.kim",
        "thread_subject": "PO 44817 promised date", "body": "Hi Laura, the guys at PMI can ship on 2026-03-20.",
        "attachments": [], "_entity_refs": ["ENT_000000000001 :: PMI"],
        "title_field_name": "subject", "content_field_names": ["body"], "dataset_doc_uuid": "dsid_mail"})
    _write(tmp_path, "teams/purchasing/2026-02-11-drives.json", {
        "channel": "purchasing", "started_at": "2026-02-11T08:00", "participants": ["Julia Kramer", "Tom Vance"],
        "topic": "drives backorder", "messages": ["2026-02-11 08:00 Julia Kramer: PMI late again on the drives"],
        "title_field_name": "topic", "content_field_names": ["messages"], "dataset_doc_uuid": "dsid_chat"})
    _write(tmp_path, "erp/purchase_orders/PO-44817.json", {
        "record_type": "purchase_order", "record_id": "PO-44817", "record_date": "2025-12-01", "system": "legacy",
        "status": "open", "vendor_name": "PRECISION MACHINING INC — V10482", "buyer": "Julia Kramer",
        "lines": ["line 1: 22-4410 rev C, bracket, qty 40"], "promised_date_history": ["—"], "notes": "—",
        "_entity_refs": ["ENT_000000000002 :: PO-44817"],
        "title_field_name": "record_id", "content_field_names": ["lines", "promised_date_history", "notes"],
        "dataset_doc_uuid": "dsid_po"})
    _write(tmp_path, "erp/purchase_orders/agents.md", {"not": "a doc"})  # no uuid → ignored
    return str(tmp_path)


def test_tokenize_keeps_ids_whole_and_split():
    t = tokenize("PO-44817 for part 22-4410 rev C, vendor V10482 ana.ruiz@x.com")
    assert {"po-44817", "po", "44817", "22-4410", "22", "4410", "v10482", "ana.ruiz"} <= set(t)


def test_corpus_hides_annotations_and_reads_dates_and_authors(corpus):
    docs = {d.doc_id: d for d in load_corpus(corpus)}
    assert set(docs) == {"dsid_mail", "dsid_chat", "dsid_po"}
    m = docs["dsid_mail"]
    assert m.date_str == "2026-03-04" and m.author.startswith("Ana Ruiz") and "laura.kim@brightwaterpkg.com" in m.participants
    assert "ENT_" not in m.text and "_entity_refs" not in m.text and "dataset_doc_uuid" not in m.text
    assert m.text.startswith("Re: PO 44817 promised date\n\n")
    assert docs["dsid_chat"].author == "Julia Kramer"
    assert docs["dsid_po"].author == "Julia Kramer" and docs["dsid_po"].date_str == "2025-12-01"


def test_keyword_search_honours_source_date_and_sender_filters(corpus):
    idx = KeywordIndex(load_corpus(corpus))
    ids = [d.doc_id for d, _ in idx.search("PMI", 10, Filters())]
    assert set(ids) == {"dsid_mail", "dsid_chat"}
    assert [d.doc_id for d, _ in idx.search("PMI", 10, Filters(sources=["teams"]))] == ["dsid_chat"]
    assert [d.doc_id for d, _ in idx.search("PMI", 10, Filters(date_from="2026-03-01"))] == ["dsid_mail"]
    assert [d.doc_id for d, _ in idx.search("PMI", 10, Filters(sender="julia"))] == ["dsid_chat"]
    assert [d.doc_id for d, _ in idx.search("PO 44817", 10, Filters(sources=["erp"]))] == ["dsid_po"]
    assert idx.search("zzzz-nothing", 10, Filters()) == []


def test_rrf_and_hybrid_fusion_prefers_docs_ranked_by_both(corpus):
    assert rrf([["a", "b"], ["b", "a"]])["a"] == rrf([["a", "b"], ["b", "a"]])["b"]
    docs = load_corpus(corpus)
    ids = [d.doc_id for d in docs]
    # fake embeddings: the chat is the semantic match for "supplier running late"
    vecs = {"dsid_mail": [1, 0, 0], "dsid_chat": [0, 1, 0], "dsid_po": [0, 0, 1]}
    store = VectorStore(ids, np.array([vecs[i] for i in ids], dtype=np.float32))
    embed = lambda texts: np.array([[0.1, 0.9, 0.0]] * len(texts), dtype=np.float32)  # noqa: E731
    h = HybridIndex(docs, store, embed)
    assert h.has_vectors
    top = [d.doc_id for d, _ in h.search("PMI late", 3, Filters())]
    assert top[0] == "dsid_chat"
    bm_only = HybridIndex(docs, None, None)
    assert not bm_only.has_vectors
    assert [d.doc_id for d, _ in bm_only.search("PO 44817", 2, Filters(sources=["erp"]))] == ["dsid_po"]


async def _call(server, name, args):
    res = await server.call_tool(name, args)
    return res


def test_keyword_tools_over_mcp(corpus):
    srv.load(corpus, "keyword")
    server = srv.build_server("keyword")
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert names == {"search", "list", "read"}
    out = asyncio.run(_call(server, "search", {"source": "outlook", "query": "PO 44817"}))
    hits = _payload(out)["hits"]
    assert hits and hits[0]["doc_id"] == "dsid_mail" and "PO 44817" in hits[0]["snippet"]
    listing = _payload(asyncio.run(_call(server, "list", {"source": "outlook", "path": ""})))
    assert listing["folders"] == ["laura.kim"] and listing["total_documents"] == 0
    listing = _payload(asyncio.run(_call(server, "list", {"source": "erp", "path": "purchase_orders"})))
    assert [d["doc_id"] for d in listing["documents"]] == ["dsid_po"]
    doc = _payload(asyncio.run(_call(server, "read", {"doc_id": "dsid_po"})))
    assert doc["title"] == "PO-44817" and "22-4410 rev C" in doc["text"] and doc["truncated"] is False
    assert "error" in _payload(asyncio.run(_call(server, "read", {"doc_id": "dsid_nope"})))
    assert "error" in _payload(asyncio.run(_call(server, "search", {"source": "nope", "query": "x"})))


def test_hybrid_tools_over_mcp(corpus):
    srv.load(corpus, "hybrid")
    server = srv.build_server("hybrid")
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert names == {"search", "read"}
    out = _payload(asyncio.run(_call(server, "search", {"query": "PMI", "sources": ["teams"]})))
    assert out["vectors"] is False and [h["doc_id"] for h in out["hits"]] == ["dsid_chat"]


def test_bearer_token_is_mandatory(corpus, monkeypatch):
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    srv.load(corpus, "keyword")
    with pytest.raises(RuntimeError):
        srv.build_app("keyword")
    app = srv.build_app("keyword", token="t")
    assert app is not None


def _payload(result):
    """A tool result's dict, whether the server put it in structuredContent or text."""
    if isinstance(result, dict):
        return result.get("result", result) if "result" in result else result
    sc = getattr(result, "structuredContent", None)
    if sc:
        return sc.get("result", sc)
    text = result.content[0].text if getattr(result, "content", None) else str(result)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"error": text}


def test_emulated_latency_is_off_by_default_parsed_from_env_and_declared(monkeypatch):
    """IND-982 (André): the raw arm can emulate real connector latency per source; it is
    off unless configured, and /healthz declares it so a report cannot hide it."""
    from raw_corpus_mcp import server as srv

    assert srv._parse_latency("") == {}
    assert srv._parse_latency("outlook:900, Teams:800,bad,erp:x") == {"outlook": 900, "teams": 800}
    slept: list[float] = []
    monkeypatch.setattr(srv.time if hasattr(srv, "time") else __import__("time"), "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(srv, "SOURCE_LATENCY_MS", {"outlook": 900})
    monkeypatch.setattr(srv, "SEARCH_LATENCY_MS", 400)
    srv._emulate("outlook")
    srv._emulate("erp")           # no entry → no sleep
    srv._emulate()                # the shared index
    assert slept == [0.9, 0.4]

"""The entity master at generation time (IND-982, code change C1).

Documents are generated against a *shortlist*: 20-30 entities from the master, each with
the surface forms that source is allowed to use for it (its alias convention). The model
mentions some of them and reports which, and with which exact surface form, in
`_entity_refs`. That field is the entity-resolution gold for the document.

Two rules keep the gold clean:

* Canonical ids (`ENT_…`) never reach the model. The shortlist uses local keys `E1…E30`;
  `apply_entity_refs` maps them back after generation and refuses anything that is not
  on the shortlist.
* A reference counts only if its surface form appears verbatim in the document text
  (title + content + metadata). Everything else is dropped, and the drop is counted so
  `validate_entity_refs` can report the rate per source.

The stored form is flat (`["ENT_xxx :: surface form", ...]`) because the corpus schema
allows only strings and lists of strings. Keys starting with `_` are stripped on export
(C4), so neither the ids nor the refs ever leave `generated_data/`.
"""

from __future__ import annotations

import json
import os
import random
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

ENTITY_MASTER_PATH = os.environ.get("ENTITY_MASTER_PATH", "gold/entity_master.json")
REFS_KEY = "_entity_refs"
SEP = " :: "
_ENT_RE = re.compile(r"ENT_[0-9a-f]{12}")

# How many of each type a shortlist carries, per source. Tuned to what the source's
# agents.md says its documents talk about.
SHORTLIST_SHAPE: dict[str, dict[str, int]] = {
    "outlook": {
        "customer": 3,
        "supplier": 4,
        "external_person": 6,
        "purchase_order": 3,
        "sales_order": 2,
        "quote": 2,
        "part": 4,
        "customer_site": 2,
    },
    "teams": {
        "customer": 3,
        "supplier": 4,
        "external_person": 2,
        "purchase_order": 4,
        "sales_order": 3,
        "quote": 1,
        "part": 5,
        "customer_site": 2,
    },
    "sharepoint": {
        "customer": 3,
        "supplier": 3,
        "external_person": 3,
        "purchase_order": 2,
        "sales_order": 3,
        "quote": 3,
        "part": 5,
        "customer_site": 2,
    },
    "hubspot": {
        "customer": 4,
        "supplier": 0,
        "external_person": 6,
        "purchase_order": 0,
        "sales_order": 2,
        "quote": 4,
        "part": 1,
        "customer_site": 3,
    },
    "quality": {
        "customer": 1,
        "supplier": 4,
        "external_person": 2,
        "purchase_order": 4,
        "sales_order": 2,
        "quote": 0,
        "part": 6,
        "customer_site": 1,
    },
    "erp": {
        "customer": 3,
        "supplier": 4,
        "external_person": 2,
        "purchase_order": 4,
        "sales_order": 3,
        "quote": 2,
        "part": 5,
        "customer_site": 1,
    },
}
_DEFAULT_SHAPE = SHORTLIST_SHAPE["outlook"]


@dataclass
class Master:
    entities: list[dict]
    by_id: dict[str, dict] = field(default_factory=dict)
    by_type: dict[str, list[dict]] = field(default_factory=dict)
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.by_id = {e["id"]: e for e in self.entities}
        for e in self.entities:
            self.by_type.setdefault(e["type"], []).append(e)

    def related(self, e: dict) -> list[dict]:
        """Entities one hop away (relations are ids or lists of ids)."""
        out = []
        for v in e.get("relations", {}).values():
            for i in (v if isinstance(v, list) else [v]):
                if i in self.by_id:
                    out.append(self.by_id[i])
        return out


@lru_cache(maxsize=1)
def load_master(path: str | None = None) -> Master | None:
    path = path or ENTITY_MASTER_PATH
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    m = Master(data["entities"])
    m.meta = {k: v for k, v in data.items() if k != "entities"}
    return m


def surface_forms(e: dict, source: str) -> list[str]:
    """The forms this source may use for the entity, deduplicated, most formal first."""
    forms = list(e.get("aliases", {}).get(source, []))
    if not forms:  # a source with no convention falls back to the canonical name
        forms = [e["name"]]
    seen: set[str] = set()
    out = []
    for f in forms:
        f = " ".join(str(f).split())
        if f and f.lower() not in seen and "ENT_" not in f:
            seen.add(f.lower())
            out.append(f)
    return out[:6]


def _describe(e: dict, m: Master) -> str:
    a = e.get("attributes", {})
    t = e["type"]
    if t == "customer":
        return (
            f"customer ({a.get('industry', '')}, {a.get('hq_city', '')} {a.get('hq_state', '')}); legacy id {a.get('legacy_id')}"
            + (f", new ERP id {a['new_id']}" if a.get("new_id") else "")
            + (
                f"; formerly {a['former_name']} until {a['rename_effective']}"
                if a.get("former_name")
                else ""
            )
        )
    if t == "supplier":
        return (
            f"supplier of {a.get('commodity', '')} ({a.get('hq_city', '')} {a.get('hq_state', '')}, {a.get('size', '')}); legacy id {a.get('legacy_id')}"
            + (f", new ERP id {a['new_id']}" if a.get("new_id") else "")
            + ("; writes from gmail.com" if a.get("domain") == "gmail.com" else "")
            + (
                f"; formerly {a['former_name']} until {a['rename_effective']}"
                if a.get("former_name")
                else ""
            )
        )
    if t == "external_person":
        emp = m.by_id.get(e.get("relations", {}).get("employer", ""), {})
        s = f"{a.get('title', '')} at {emp.get('name', '?')}, {a.get('email', '')}"
        if a.get("employer_change_effective"):
            old = m.by_id.get(e["relations"].get("former_employer", ""), {})
            s += f" (moved from {old.get('name', '?')} on {a['employer_change_effective']})"
        return s
    if t == "part":
        v = m.by_id.get(e.get("relations", {}).get("primary_vendor", ""), {})
        s = f"part: {a.get('description', '')} ({a.get('family', '')}), supplier P/N {a.get('supplier_part_number')}, from {v.get('name', '?')}"
        if a.get("superseded_by_revision"):
            s += f"; rev {a['revision']} superseded by rev {a['superseded_by_revision']} on {a['supersession_effective']} (old supplier P/N {a.get('previous_supplier_part_number')})"
        if a.get("obsolete") == "yes":
            s += f"; OBSOLETE, end of life {a.get('end_of_life')}"
        return s
    if t == "purchase_order":
        v = m.by_id.get(e.get("relations", {}).get("vendor", ""), {})
        s = f"PO to {v.get('name', '?')} dated {a.get('order_date')}, buyer {a.get('buyer')}, ship to {a.get('ship_to')}, promised {a.get('promised_date_original')}"
        if a.get("promised_date_history"):
            s += f", revised to {a.get('promised_date_current')} ({len(a['promised_date_history'])} changes: {'; '.join(a['promised_date_history'])})"
        if a.get("machine_job"):
            s += f", for job {a['machine_job']}"
        return s + f", status {a.get('status')}"
    if t == "sales_order":
        c = m.by_id.get(e.get("relations", {}).get("customer", ""), {})
        s = f"sales order / job {a.get('machine_job')} for {c.get('name', '?')}: {a.get('machine_type')}, ordered {a.get('order_date')}, ship {a.get('current_ship_date')}, built in {a.get('build_site')}, PM {a.get('project_manager')}"
        if a.get("ship_date_history"):
            s += f" (ship date changes: {'; '.join(a['ship_date_history'])})"
        return s
    if t == "quote":
        c = m.by_id.get(e.get("relations", {}).get("customer", ""), {})
        return f"quote / {a.get('rfq_number')} to {c.get('name', '?')} for a {a.get('machine_type')}, {a.get('date')}, ${a.get('amount_usd')}, rev {a.get('revision')}, {a.get('status')}, owner {a.get('owner')}"
    if t == "customer_site":
        return f"plant of {m.by_id.get(e['relations'].get('customer', ''), {}).get('name', '?')} in {a.get('city')}, {a.get('state')} ({a.get('plant_kind')}, {a.get('lines')} lines)"
    return t


@dataclass
class Shortlist:
    source: str
    entries: list[tuple[str, dict]]  # (local key, entity)

    def prompt_block(self, m: Master) -> str:
        lines = [
            "## Entities you may mention",
            "The following real entities exist in this company's world. When your document refers to one of them, "
            "use ONLY the surface forms listed for it (pick whichever fits the sentence; you may use several). "
            "You do not have to mention all of them — mention the ones that fit the document naturally, typically "
            "3 to 10. Do NOT invent other customers, suppliers, external people, purchase orders, sales orders, "
            "quotes, RFQs, part numbers or plants: every such reference in the document must be one of the "
            "entities below, written with one of its surface forms (employees of our own company come from the "
            "company context). Never write the bracketed keys (E1, E2, ...) inside the document.",
            "",
        ]
        for key, e in self.entries:
            forms = " | ".join(f'"{f}"' for f in surface_forms(e, self.source))
            lines.append(f"- [{key}] {_describe(e, m)}. Surface forms: {forms}")
        lines += [
            "",
            f'In the JSON you output, add a field "{REFS_KEY}": a list of strings, one per mention you made, in the form '
            f'"<key>{SEP}<exact surface form as written in the document>", e.g. ["E3{SEP}PMI", "E7{SEP}PO 44817"]. '
            "List every entity from the list above that the document mentions, with the exact spelling you used. "
            "This field is an internal annotation and is not part of the document's visible content.",
        ]
        return "\n".join(lines)


def _pick(
    rng: random.Random,
    pool: list[dict],
    n: int,
    weights: dict[str, float] | None = None,
) -> list[dict]:
    if n <= 0 or not pool:
        return []
    n = min(n, len(pool))
    if weights:
        w = [weights.get(e["id"], 1.0) for e in pool]
        chosen: list[dict] = []
        cand = list(pool)
        cw = list(w)
        for _ in range(n):
            i = rng.choices(range(len(cand)), weights=cw, k=1)[0]
            chosen.append(cand.pop(i))
            cw.pop(i)
        return chosen
    return rng.sample(pool, n)


def _popularity(m: Master) -> dict[str, float]:
    """A stable Zipf-like weight per company so a few counterparties dominate the corpus,
    the way a real company's mail does (the same seed every run)."""
    w: dict[str, float] = {}
    for t in ("customer", "supplier"):
        pool = m.by_type.get(t, [])
        order = sorted(pool, key=lambda e: e["id"])
        r = random.Random(f"popularity|{t}")
        r.shuffle(order)
        for rank, e in enumerate(order, start=1):
            w[e["id"]] = 1.0 / (rank**0.8)
    return w


def build_shortlist(
    m: Master,
    source: str,
    seed: str,
    *,
    anchors: list[str] | None = None,
    shape: dict[str, int] | None = None,
) -> Shortlist:
    """A coherent 20-30 entity shortlist for one document.

    `anchors` are entity ids the document must be about (a project's attached entities,
    or the record an ERP document renders); the rest is filled with their neighbours and
    then popularity-weighted random picks, so documents share counterparties.
    """
    rng = random.Random(f"{source}|{seed}")
    shape = dict(shape or SHORTLIST_SHAPE.get(source, _DEFAULT_SHAPE))
    pop = _popularity(m)
    chosen: dict[str, dict] = {}

    def add(e: dict) -> None:
        if e["id"] not in chosen and len(chosen) < 30:
            chosen[e["id"]] = e

    for i in anchors or []:
        if i in m.by_id:
            add(m.by_id[i])
    # neighbours of the anchors: the people at those companies, the POs to those suppliers…
    for e in list(chosen.values()):
        for r in m.related(e):
            add(r)
    # companies first (weighted), then their people / documents so the list is coherent
    companies = _pick(
        rng, m.by_type.get("customer", []), shape.get("customer", 0), pop
    ) + _pick(rng, m.by_type.get("supplier", []), shape.get("supplier", 0), pop)
    for c in companies:
        add(c)
    company_ids = {
        e["id"] for e in chosen.values() if e["type"] in ("customer", "supplier")
    }

    def linked(t: str, rel: str) -> list[dict]:
        return [
            e
            for e in m.by_type.get(t, [])
            if e.get("relations", {}).get(rel) in company_ids
        ]

    for t, rel in (
        ("external_person", "employer"),
        ("purchase_order", "vendor"),
        ("sales_order", "customer"),
        ("quote", "customer"),
        ("customer_site", "customer"),
    ):
        want = shape.get(t, 0)
        have = sum(1 for e in chosen.values() if e["type"] == t)
        for e in _pick(rng, linked(t, rel), max(0, want - have)):
            add(e)
    # parts: those on the chosen POs first, then random
    po_parts = [
        m.by_id[i]
        for e in chosen.values()
        if e["type"] == "purchase_order"
        for i in e.get("relations", {}).get("lines", [])
        if i in m.by_id
    ]
    have = sum(1 for e in chosen.values() if e["type"] == "part")
    for e in po_parts[: max(0, shape.get("part", 0) - have)]:
        add(e)
    have = sum(1 for e in chosen.values() if e["type"] == "part")
    for e in _pick(rng, m.by_type.get("part", []), max(0, shape.get("part", 0) - have)):
        add(e)
    entries = [(f"E{i + 1}", e) for i, e in enumerate(chosen.values())]
    return Shortlist(source, entries)


# Models write typographic characters (non-breaking hyphen U+2011, en dash, curly quotes,
# NBSP) where the master has ASCII. Both the stored document and the verbatim check are
# normalised to ASCII punctuation, so "PO‑45281" and "PO-45281" are the same mention and
# the corpus itself is clean for every downstream reader.
_ASCII_MAP = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u00a0": " ",
        "\u202f": " ",
        "\u2009": " ",
        "\u2026": "...",
    }
)


def normalize_text(s: str) -> str:
    return s.translate(_ASCII_MAP)


def normalize_doc(doc: dict) -> dict:
    """ASCII-punctuation every string value (and list of strings) in place."""
    for k, v in list(doc.items()):
        if isinstance(v, str):
            doc[k] = normalize_text(v)
        elif isinstance(v, list):
            doc[k] = [normalize_text(x) if isinstance(x, str) else x for x in v]
    return doc


def _document_text(doc: dict) -> str:
    parts = []
    for k, v in doc.items():
        if k.startswith("_") or k in (
            "title_field_name",
            "content_field_names",
            "dataset_doc_uuid",
        ):
            continue
        if isinstance(v, list):
            parts.append("\n".join(str(x) for x in v))
        else:
            parts.append(str(v))
    return normalize_text("\n".join(parts))


def apply_entity_refs(doc: dict, shortlist: Shortlist) -> tuple[dict, dict]:
    """Map the model's `E<n> :: form` refs to canonical ids, keeping only refs whose form
    appears verbatim in the document. Returns (doc, report)."""
    normalize_doc(doc)
    raw = doc.get(REFS_KEY) or []
    if not isinstance(raw, list):
        raw = [str(raw)]
    keys = {k: e for k, e in shortlist.entries}
    text = _document_text(doc)
    kept: list[str] = []
    dropped: list[str] = []
    seen: set[str] = set()
    for item in raw:
        s = str(item)
        if SEP not in s:
            dropped.append(s)
            continue
        key, form = s.split(SEP, 1)
        key, form = key.strip().strip("[]"), normalize_text(" ".join(form.split()))
        e = keys.get(key)
        if e is None or not form:
            dropped.append(s)
            continue
        if form not in text:
            # The model named the right entity but cited a form it did not write
            # (it says "MidNation Controls Supply LLC", the text says "MidNation").
            # Keep the mention with the longest of the entity's forms that IS verbatim.
            alt = next(
                (
                    f
                    for f in sorted(
                        surface_forms(e, shortlist.source), key=len, reverse=True
                    )
                    if normalize_text(f) in text
                ),
                None,
            )
            if alt is None:
                dropped.append(s)
                continue
            form = normalize_text(alt)
        line = f"{e['id']}{SEP}{form}"
        if line not in seen:
            seen.add(line)
            kept.append(line)
    # The model's self-report under-cites (it forgets mentions it wrote) and over-cites
    # (it lists shortlist entities it never wrote). The gold cannot depend on either:
    # every DISTINCTIVE surface form of a shortlist entity that appears verbatim in the
    # text is a mention, found by dictionary matching with word boundaries and
    # longest-match overlap resolution (so a near-name twin's shorter form inside the
    # longer name does not count). Short, generic forms ("Marcus", "GP") are only
    # accepted on the model's word.
    for line in scan_mentions(text, shortlist):
        if line not in seen:
            seen.add(line)
            kept.append(line)
    doc[REFS_KEY] = kept
    return doc, {"kept": len(kept), "dropped": len(dropped), "dropped_items": dropped}


def is_distinctive(form: str) -> bool:
    f = form.strip()
    if any(c.isdigit() for c in f) or "@" in f:
        return True
    words = f.split()
    if len(words) >= 2 and len(f) >= 10:
        return True
    return len(f) >= 14


_BOUNDARY = r"(?<![A-Za-z0-9])"
_BOUNDARY_END = r"(?![A-Za-z0-9])"


def _bounded(form: str) -> str:
    """A regex for `form` with word boundaries only where the form itself starts or
    ends with a letter or digit ("@precisionmach.com" may follow "ana")."""
    pat = re.escape(form)
    if form[:1].isalnum():
        pat = _BOUNDARY + pat
    if form[-1:].isalnum():
        pat = pat + _BOUNDARY_END
    return pat


def scan_mentions(text: str, shortlist: "Shortlist") -> list[str]:
    """`ENT :: form` for every distinctive shortlist form found verbatim in `text`."""
    spans: list[tuple[int, int, str, str]] = []  # start, end, entity id, form
    low = text.lower()
    for _key, e in shortlist.entries:
        for form in surface_forms(e, shortlist.source):
            nf = normalize_text(form)
            if not is_distinctive(nf):
                continue
            pat = _bounded(nf)
            for m in (
                re.finditer(pat, text)
                if any(c.isupper() for c in nf)
                else re.finditer(pat, low)
            ):
                spans.append((m.start(), m.end(), e["id"], nf))
    # longest match wins where spans overlap
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    chosen: list[tuple[int, int, str, str]] = []
    last_end = -1
    for st, en, eid, form in spans:
        if st < last_end:
            continue
        chosen.append((st, en, eid, form))
        last_end = en
    out: list[str] = []
    seen: set[str] = set()
    for _st, _en, eid, form in chosen:
        line = f"{eid}{SEP}{form}"
        if line not in seen:
            seen.add(line)
            out.append(line)
    return out


_LOG_LOCK = __import__("threading").Lock()
ENTITY_REFS_LOG = os.path.join("generation_cache", "entity_refs_log.jsonl")


def log_entity_refs(path: str, report: dict) -> None:
    """One line per generated document: how many refs the model emitted were kept and
    how many were dropped. `validate_entity_refs` turns this into the drop rate per source
    (target < 5%)."""
    line = json.dumps(
        {
            "path": path,
            "source": entity_source_for_path(path),
            "kept": report.get("kept", 0),
            "dropped": report.get("dropped", 0),
            "dropped_items": report.get("dropped_items", [])[:10],
        }
    )
    with _LOG_LOCK:
        os.makedirs(os.path.dirname(ENTITY_REFS_LOG), exist_ok=True)
        with open(ENTITY_REFS_LOG, "a") as f:
            f.write(line + "\n")


def leaks(doc: dict) -> list[str]:
    """Canonical ids that reached the document text — must always be empty."""
    return _ENT_RE.findall(_document_text(doc))


def refs_to_pairs(doc: dict) -> list[tuple[str, str]]:
    out = []
    for s in doc.get(REFS_KEY) or []:
        if SEP in str(s):
            cid, form = str(s).split(SEP, 1)
            out.append((cid, form))
    return out


def entity_source_for_path(path: str) -> str:
    """`sources/outlook/...` → `outlook`."""
    parts = [p for p in path.replace("\\", "/").split("/") if p]
    if parts and parts[0] == "sources" and len(parts) > 1:
        return parts[1]
    return parts[0] if parts else ""


def shortlist_for_document(
    m: Master, file_path: str, *, anchors: list[str] | None = None, extra_seed: str = ""
) -> Shortlist:
    return build_shortlist(
        m,
        entity_source_for_path(file_path),
        f"{file_path}|{extra_seed}",
        anchors=anchors,
    )


def anchors_from_project(project_json: dict[str, Any]) -> list[str]:
    """Entity ids a project was given by step 6 (C2)."""
    out = []
    for e in project_json.get("entities", []) or []:
        i = e.get("id") if isinstance(e, dict) else e
        if isinstance(i, str) and _ENT_RE.fullmatch(i):
            out.append(i)
    return out


# ── whole-master scan (documents that were written without a shortlist) ─────
_ALL_SCAN_CACHE: dict[tuple[int, str], tuple[re.Pattern, dict[str, str]]] = {}


def _all_forms_pattern(m: Master, source: str) -> tuple[re.Pattern, dict[str, str]]:
    key = (id(m), source)
    if key not in _ALL_SCAN_CACHE:
        forms: dict[str, str] = {}
        for e in m.entities:
            for f in surface_forms(e, source):
                nf = normalize_text(f)
                if is_distinctive(nf) and nf not in forms:
                    forms[nf] = e["id"]
        alts = sorted(forms, key=len, reverse=True)
        pat = re.compile("(" + "|".join(_bounded(a) for a in alts) + ")")
        _ALL_SCAN_CACHE[key] = (pat, forms)
    return _ALL_SCAN_CACHE[key]


def scan_all_mentions(text: str, m: Master, source: str) -> list[str]:
    """`ENT :: form` for every distinctive form of ANY master entity found verbatim —
    for documents generated without a shortlist (completeness clusters, misc files,
    near-duplicates). One alternation regex, longest alternative first."""
    pat, forms = _all_forms_pattern(m, source)
    out: list[str] = []
    seen: set[str] = set()
    for mt in pat.finditer(text):
        form = mt.group(1)
        line = f"{forms[form]}{SEP}{form}"
        if line not in seen:
            seen.add(line)
            out.append(line)
    return out

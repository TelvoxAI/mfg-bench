"""Re-apply the entity refs the model emitted, with the current matching rules, without
a model call (IND-982 C1 follow-up).

`generation_cache/entity_refs_log.jsonl` keeps, per generated document, the refs that
were dropped at write time. When the matching rules improve (punctuation normalisation,
alias fallback), this rebuilds the document's shortlist — deterministic from its path
and its project's entities — re-applies every logged ref (kept + dropped), normalises the
document text, and rewrites the file.

Usage:
    python -m src.scripts.util_scripts.repair_entity_refs
"""

from __future__ import annotations

import json
import os
from collections import defaultdict

from src.entities.master import (
    REFS_KEY,
    SEP,
    anchors_from_project,
    apply_entity_refs,
    build_shortlist,
    entity_source_for_path,
    load_master,
    shortlist_for_document,
)
from src.paths import PROJECTS_DIR
from src.utils.file_io import load_json_file, write_json_file

LOG = os.path.join("generation_cache", "entity_refs_log.jsonl")


def _project_anchors() -> dict[str, list[str]]:
    """file path → the entity ids of the project that planned it (step 7 documents)."""
    out: dict[str, list[str]] = {}
    if not os.path.isdir(PROJECTS_DIR):
        return out
    for fn in os.listdir(PROJECTS_DIR):
        if not fn.endswith(".json"):
            continue
        pj = load_json_file(os.path.join(PROJECTS_DIR, fn))
        anchors = anchors_from_project(pj)
        for f in pj.get("files", []):
            out[f.get("path", "")] = anchors
    return out


def scan_unreferenced(m) -> dict[str, int]:
    """Documents written without a shortlist (step 8 clusters, misc files, near
    duplicates) get their mentions from a whole-master scan of distinctive forms."""
    from src.entities.master import normalize_doc, scan_all_mentions
    from src.paths import SOURCES_DIR

    stats: dict[str, int] = defaultdict(int)
    for root, _dirs, files in os.walk(SOURCES_DIR):
        for fn in files:
            if not fn.endswith(".json"):
                continue
            path = os.path.join(root, fn)
            try:
                doc = load_json_file(path)
            except Exception:
                continue
            if REFS_KEY in doc or not doc.get("dataset_doc_uuid"):
                continue
            source = entity_source_for_path(
                os.path.relpath(path, os.path.dirname(SOURCES_DIR))
            )
            normalize_doc(doc)
            from src.entities.master import _document_text

            doc[REFS_KEY] = scan_all_mentions(_document_text(doc), m, source)
            write_json_file(path, doc)
            stats["docs"] += 1
            stats["mentions"] += len(doc[REFS_KEY])
    return dict(stats)


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--scan-unreferenced",
        action="store_true",
        help="also annotate documents that have no _entity_refs at all (whole-master scan)",
    )
    args = ap.parse_args()
    m = load_master()
    if m is None:
        raise SystemExit("entity master not found")
    if args.scan_unreferenced:
        print("unreferenced:", scan_unreferenced(m))
    anchors = _project_anchors()
    # every ref the model emitted, per document (the last log line per path wins)
    emitted: dict[str, list[str]] = {}
    with open(LOG, encoding="utf-8") as f:
        for ln in f:
            if not ln.strip():
                continue
            r = json.loads(ln)
            emitted[r["path"]] = list(r.get("dropped_items", []))
    stats = defaultdict(int)
    for rel, dropped in emitted.items():
        path = (
            os.path.join("generated_data", rel)
            if not rel.startswith("generated_data")
            else rel
        )
        if not os.path.exists(path):
            stats["missing"] += 1
            continue
        doc = load_json_file(path)
        # the refs kept at write time are canonical already; keep them, re-try the dropped
        kept = [x for x in (doc.get(REFS_KEY) or []) if SEP in str(x)]
        if rel in anchors:
            sl = shortlist_for_document(m, rel, anchors=anchors[rel])
        else:
            # step 9 documents: the shortlist seed was topic-based and is not logged, so
            # only the punctuation fix applies to their kept refs
            sl = None
        if sl is not None and dropped:
            doc[REFS_KEY] = dropped
            doc, rep = apply_entity_refs(doc, sl)
            recovered = [x for x in doc[REFS_KEY] if x not in kept]
            doc[REFS_KEY] = kept + recovered
            stats["recovered"] += len(recovered)
            stats["still_dropped"] += rep["dropped"]
        else:
            from src.entities.master import normalize_doc

            normalize_doc(doc)
            doc[REFS_KEY] = kept
        write_json_file(path, doc)
        stats["docs"] += 1
    print(dict(stats))


if __name__ == "__main__":
    main()

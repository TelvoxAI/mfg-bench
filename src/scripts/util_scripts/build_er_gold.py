"""Build the entity-resolution gold from the annotated corpus (IND-982, C6).

Reads every document under `generated_data/sources/` that carries `_entity_refs` and the
entity master, and writes:

* `<out>/er_gold/mentions.jsonl` — one line per (document, surface form, canonical id):
  `{"doc_id": "dsid_…", "source": "outlook", "surface_form": "PMI", "canonical_id": "ENT_…",
    "entity_type": "supplier"}`
* `<out>/er_gold/clusters.jsonl` — one line per entity that is mentioned at least once:
  `{"canonical_id", "entity_type", "canonical_name", "doc_ids": [...], "surface_forms": [...],
    "hard_case": "..."}`
* `<out>/er_gold/summary.json` — counts per source and type, hard-case coverage.

The gold comes from the annotations, not from a model reading the documents: a mention
exists only where the generator recorded it and the form appears verbatim. Run
`validate_entity_refs --fix` first.

Usage:
    python -m src.scripts.util_scripts.build_er_gold [--out gold]
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict

from src.entities.master import _document_text, load_master, refs_to_pairs
from src.paths import SOURCES_DIR
from src.utils.file_io import load_json_file


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="gold")
    args = ap.parse_args()
    m = load_master()
    if m is None:
        raise SystemExit("entity master not found (ENTITY_MASTER_PATH)")
    out_dir = os.path.join(args.out, "er_gold")
    os.makedirs(out_dir, exist_ok=True)

    mentions = 0
    clusters: dict[str, dict] = {}
    per_source: dict[str, int] = defaultdict(int)
    per_type: dict[str, int] = defaultdict(int)
    docs_with_refs = 0
    skipped_unverified = 0
    with open(os.path.join(out_dir, "mentions.jsonl"), "w") as mf:
        for root, _dirs, files in os.walk(SOURCES_DIR):
            for fn in files:
                if not fn.endswith(".json"):
                    continue
                path = os.path.join(root, fn)
                try:
                    doc = load_json_file(path)
                except Exception:
                    continue
                pairs = refs_to_pairs(doc)
                doc_id = doc.get("dataset_doc_uuid")
                if not pairs or not doc_id:
                    continue
                docs_with_refs += 1
                source = os.path.relpath(path, SOURCES_DIR).split(os.sep)[0]
                text = _document_text(doc)
                for cid, form in pairs:
                    e = m.by_id.get(cid)
                    if e is None or form not in text:
                        skipped_unverified += 1
                        continue
                    mf.write(
                        json.dumps(
                            {
                                "doc_id": doc_id,
                                "source": source,
                                "surface_form": form,
                                "canonical_id": cid,
                                "entity_type": e["type"],
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    mentions += 1
                    per_source[source] += 1
                    per_type[e["type"]] += 1
                    c = clusters.setdefault(
                        cid,
                        {
                            "canonical_id": cid,
                            "entity_type": e["type"],
                            "canonical_name": e["name"],
                            "doc_ids": [],
                            "surface_forms": [],
                            "hard_case": e["attributes"].get("hard_case", ""),
                        },
                    )
                    if doc_id not in c["doc_ids"]:
                        c["doc_ids"].append(doc_id)
                    if form not in c["surface_forms"]:
                        c["surface_forms"].append(form)
    with open(os.path.join(out_dir, "clusters.jsonl"), "w") as cf:
        for c in sorted(
            clusters.values(), key=lambda c: (-len(c["doc_ids"]), c["canonical_id"])
        ):
            cf.write(json.dumps(c, ensure_ascii=False) + "\n")
    hard = defaultdict(int)
    for c in clusters.values():
        if c["hard_case"]:
            hard[c["hard_case"]] += 1
    summary = {
        "documents_with_refs": docs_with_refs,
        "mentions": mentions,
        "entities_mentioned": len(clusters),
        "entities_in_master": len(m.entities),
        "skipped_unverified": skipped_unverified,
        "mentions_per_source": dict(per_source),
        "mentions_per_type": dict(per_type),
        "hard_case_entities_mentioned": dict(hard),
        "multi_form_entities": sum(
            1 for c in clusters.values() if len(c["surface_forms"]) > 1
        ),
        "multi_source_entities": sum(
            1 for c in clusters.values() if len({s for s in c["doc_ids"]}) > 1
        ),
    }
    with open(os.path.join(out_dir, "summary.json"), "w") as sf:
        json.dump(summary, sf, indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()

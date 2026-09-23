"""Verify the entity-resolution annotations of the generated corpus (IND-982, C3).

For every document under `generated_data/sources/` that carries `_entity_refs`:

* each surface form must appear verbatim in the document text; a ref that does not is
  dropped (with `--fix`, the file is rewritten without it);
* no canonical id (`ENT_…`) may appear anywhere in the document text — that is a leak
  and fails the run;
* the drop rate is reported per source, both for what the model emitted at generation
  time (`generation_cache/entity_refs_log.jsonl`, written by steps 7 and 9) and for what
  is on disk now. The target is < 5% per source; the exit code is 1 above it.

Usage:
    python -m src.scripts.util_scripts.validate_entity_refs [--fix] [--max-drop-rate 5.0]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

from src.entities.master import (
    ENTITY_REFS_LOG,
    REFS_KEY,
    SEP,
    _document_text,
    leaks,
    load_master,
    normalize_text,
)
from src.paths import SOURCES_DIR
from src.utils.file_io import load_json_file, write_json_file


def _source_of(path: str) -> str:
    rel = os.path.relpath(path, SOURCES_DIR)
    return rel.split(os.sep)[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--fix", action="store_true", help="rewrite documents without the invalid refs"
    )
    ap.add_argument(
        "--max-drop-rate", type=float, default=5.0, help="percent, per source"
    )
    args = ap.parse_args()
    master = load_master()
    known = master.by_id if master else {}

    stats: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    leaked: list[tuple[str, list[str]]] = []
    for root, _dirs, files in os.walk(SOURCES_DIR):
        for fn in files:
            if not fn.endswith(".json"):
                continue
            path = os.path.join(root, fn)
            src = _source_of(path)
            try:
                doc = load_json_file(path)
            except Exception:
                stats[src]["unreadable"] += 1
                continue
            stats[src]["docs"] += 1
            leak = leaks(doc)
            if leak:
                leaked.append((path, leak))
            refs = doc.get(REFS_KEY)
            if not isinstance(refs, list):
                stats[src]["docs_without_refs"] += 1
                continue
            stats[src]["docs_with_refs"] += 1
            text = _document_text(doc)
            kept = []
            for r in refs:
                s = str(r)
                stats[src]["refs"] += 1
                if SEP not in s:
                    stats[src]["invalid_format"] += 1
                    continue
                cid, form = s.split(SEP, 1)
                if known and cid not in known:
                    stats[src]["unknown_entity"] += 1
                    continue
                if normalize_text(form) not in text:
                    stats[src]["not_verbatim"] += 1
                    continue
                kept.append(s)
            stats[src]["verified"] += len(kept)
            if args.fix and len(kept) != len(refs):
                doc[REFS_KEY] = kept
                write_json_file(path, doc)
                stats[src]["files_fixed"] += 1

    # what the model emitted at generation time (before apply_entity_refs dropped anything)
    emitted: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    if os.path.exists(ENTITY_REFS_LOG):
        with open(ENTITY_REFS_LOG) as f:
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                emitted[row.get("source", "?")]["kept"] += int(row.get("kept", 0))
                emitted[row.get("source", "?")]["dropped"] += int(row.get("dropped", 0))

    print(
        f"{'source':<12}{'docs':>7}{'with refs':>10}{'refs':>7}{'verified':>9}{'on-disk drop':>13}{'model drop':>12}"
    )
    failed = False
    for src in sorted(stats):
        s = stats[src]
        refs = s["refs"]
        disk_drop = 100.0 * (refs - s["verified"]) / refs if refs else 0.0
        em = emitted.get(src, {})
        em_total = em.get("kept", 0) + em.get("dropped", 0)
        model_drop = 100.0 * em.get("dropped", 0) / em_total if em_total else 0.0
        flag = ""
        if (
            refs
            and disk_drop > args.max_drop_rate
            or em_total
            and model_drop > args.max_drop_rate
        ):
            flag = "  <-- above target"
            failed = True
        print(
            f"{src:<12}{s['docs']:>7}{s['docs_with_refs']:>10}{refs:>7}{s['verified']:>9}{disk_drop:>12.1f}%{model_drop:>11.1f}%{flag}"
        )
    if leaked:
        failed = True
        print(f"\nCANONICAL ID LEAKS in {len(leaked)} documents (must be zero):")
        for path, ids in leaked[:20]:
            print(f"  {path}: {ids}")
    if not stats:
        print("no documents found under", SOURCES_DIR)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

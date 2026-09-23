"""Entity refs (IND-982 C1): normalisation, alias fallback, dictionary scan with
longest-match overlap, and the model's self-report kept honest."""

from src.entities.master import Master, Shortlist, apply_entity_refs, normalize_text, scan_mentions


def _master():
    ents = [
        {"id": "ENT_000000000001", "type": "supplier", "name": "Precision Machining Inc.", "attributes": {}, "relations": {},
         "aliases": {"outlook": ["Precision Machining Inc.", "PMI", "@precisionmach.com", "the guys at PMI"], "teams": ["PMI", "Precison"]}},
        {"id": "ENT_000000000002", "type": "supplier", "name": "Precision Machining Works LLC", "attributes": {}, "relations": {},
         "aliases": {"outlook": ["Precision Machining Works LLC", "Precision Machining Works"], "teams": ["PMW"]}},
        {"id": "ENT_000000000003", "type": "purchase_order", "name": "PO-44817", "attributes": {}, "relations": {},
         "aliases": {"outlook": ["PO 44817", "po#44817", "PO-44817"], "teams": ["44817"]}},
        {"id": "ENT_000000000004", "type": "external_person", "name": "Marcus Austin", "attributes": {}, "relations": {},
         "aliases": {"outlook": ["Marcus Austin", "Marcus", "Marcus A."], "teams": ["Marcus", "MA"]}},
    ]
    return Master(ents)


def _shortlist(m, source="outlook"):
    return Shortlist(source, [(f"E{i + 1}", e) for i, e in enumerate(m.entities)])


def test_normalisation_makes_typographic_punctuation_ascii():
    assert normalize_text("PO‑44817 – “ok” x") == 'PO-44817 - "ok" x'


def test_scan_finds_distinctive_forms_and_resolves_the_twin_by_longest_match():
    m = _master()
    text = "Precision Machining Works LLC quoted PO-44817 yesterday; Marcus said PMI is slow."
    found = scan_mentions(text, _shortlist(m))
    assert "ENT_000000000002 :: Precision Machining Works LLC" in found
    assert "ENT_000000000003 :: PO-44817" in found
    assert not any(x.startswith("ENT_000000000001 :: Precision Machining") for x in found)  # twin's prefix not counted
    assert "ENT_000000000004 :: Marcus" not in found  # short generic form: model's word only
    assert "ENT_000000000001 :: PMI" not in found  # 3 letters, not distinctive


def test_apply_keeps_model_refs_that_are_verbatim_falls_back_to_aliases_and_adds_scanned_mentions():
    m = _master()
    doc = {"subject": "Re: PO‑44817", "body": "Marcus, the guys at PMI slipped PO‑44817 to 2026-03-20. Ping ana@precisionmach.com",
           "_entity_refs": ["E4 :: Marcus", "E1 :: Precision Machining Inc.", "E3 :: po#44817", "E2 :: PMW"]}
    doc, rep = apply_entity_refs(doc, _shortlist(m))
    refs = doc["_entity_refs"]
    assert doc["subject"] == "Re: PO-44817"  # document normalised in place
    assert "ENT_000000000004 :: Marcus" in refs  # short form accepted on the model's word
    assert "ENT_000000000001 :: the guys at PMI" in refs  # alias fallback: cited the formal name, wrote the informal one
    assert "ENT_000000000003 :: PO-44817" in refs  # cited po#44817, wrote PO-44817 → alias fallback / scan
    assert "ENT_000000000001 :: @precisionmach.com" in refs  # scanned distinctive form
    assert not any(x.startswith("ENT_000000000002") for x in refs)  # PMW never appears
    assert rep["dropped"] == 1 and rep["dropped_items"] == ["E2 :: PMW"]
    assert not any("ENT_" in v for k, v in doc.items() if k != "_entity_refs")


def test_whole_master_scan_uses_longest_alternative_first():
    from src.entities.master import scan_all_mentions

    m = _master()
    text = "Precision Machining Works LLC and PO-44817; ana@precisionmach.com wrote."
    found = scan_all_mentions(text, m, "outlook")
    assert "ENT_000000000002 :: Precision Machining Works LLC" in found
    assert "ENT_000000000003 :: PO-44817" in found
    assert "ENT_000000000001 :: @precisionmach.com" in found
    assert not any(x.startswith("ENT_000000000001 :: Precision Machining Inc") for x in found)

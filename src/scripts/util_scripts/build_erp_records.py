"""Render the ERP source deterministically from the entity master (IND-982).

ERP documents are records, not prose: a purchase order IS the purchase-order entity.
Generating them with a model would only add drift between the record and the master it
is supposed to reflect, so this script renders every vendor, customer, item, purchase
order and sales order of the master into `generated_data/sources/erp/` with the fields
the erp agents.md promises, plus shipments and invoices derived from them. The
`_entity_refs` of each record are exact by construction (the record's own entity and
everything it references, in the ERP surface form), which makes the ERP source the
anchor of the entity-resolution gold.

The ERP migration is modelled as two systems: records dated before 2026-01-04 come from
the legacy system and carry legacy ids; records after it come from the new ERP, carry
the new six-digit ids and, for migrated master records, a `legacy_id`. Every migrated
vendor and customer therefore exists twice — one master record per system.

Idempotent: existing files are left alone. Field labels and dataset uuids are set here
(no model call), so step 9's labeling pass has nothing to do for these files.

Usage:
    python -m src.scripts.util_scripts.build_erp_records [--seed 20260922]
"""

from __future__ import annotations

import argparse
import os
import random
from datetime import date, timedelta

from src.entities.master import REFS_KEY, SEP, load_master, surface_forms
from src.paths import SOURCES_DIR
from src.utils.dataset_id import add_dataset_doc_uuid
from src.utils.file_io import write_json_file

ERP_DIR = os.path.join(SOURCES_DIR, "erp")
GO_LIVE = date(2026, 1, 4)
WINDOW_START = date(2025, 4, 1)
WINDOW_END = date(2026, 9, 30)
CARRIERS = None  # filled from the master's freight suppliers


def _d(s: str) -> date:
    return date.fromisoformat(s)


def _ref(e: dict, form: str) -> str:
    return f"{e['id']}{SEP}{form}"


def _erp_form(e: dict, system: str) -> str:
    """The ERP surface form for a company in a given system."""
    forms = surface_forms(e, "erp")
    if system == "new_erp" and len(forms) > 1:
        return forms[1]
    return forms[0]


def _write(rel: str, doc: dict, title_field: str, content_fields: list[str]) -> bool:
    path = os.path.join(SOURCES_DIR, rel)
    if os.path.exists(path):
        return False
    doc["title_field_name"] = title_field
    doc["content_field_names"] = content_fields
    write_json_file(path, doc)
    add_dataset_doc_uuid(path)
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260922)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    m = load_master()
    if m is None:
        raise SystemExit("entity master not found (ENTITY_MASTER_PATH)")
    written = {
        "vendors": 0,
        "customers": 0,
        "items": 0,
        "purchase_orders": 0,
        "sales_orders": 0,
        "shipments": 0,
        "invoices": 0,
    }
    carriers = [
        s
        for s in m.by_type.get("supplier", [])
        if s["attributes"].get("commodity") == "freight carrier"
    ]
    emp_buyers = sorted(
        {e["attributes"]["buyer"] for e in m.by_type.get("purchase_order", [])}
    )

    # ── vendors and customers: one record per system ────────────────────────
    for t, folder, prefix in (
        ("supplier", "vendors", "V"),
        ("customer", "customers", "C"),
    ):
        for e in m.by_type.get(t, []):
            a = e["attributes"]
            legacy, new = a["legacy_id"], a.get("new_id", "")
            common = {
                "record_type": "vendor" if t == "supplier" else "customer",
                "legal_name": e["name"].upper() if t == "supplier" else e["name"],
                "display_name": _erp_form(e, "legacy"),
                "address": f"{rng.randrange(100, 9999)} {rng.choice(['Industrial Pkwy', 'Commerce Dr', 'Enterprise Blvd', 'Av. Industrial', 'Mill Rd', 'Airport Rd'])}",
                "city": a.get("hq_city", ""),
                "state_or_country": (
                    a.get("hq_state", "")
                    if a.get("country") == "US"
                    else f"{a.get('hq_state', '')}, Mexico"
                ),
                "payment_terms": rng.choice(
                    [
                        "Net 30",
                        "Net 45",
                        "Net 60",
                        "2% 10 Net 30",
                        "50% deposit / 50% at FAT",
                    ]
                ),
                "primary_contact": "",
                "contact_email": "",
                # every ERP vendor/customer master has a website field; a party on a
                # personal mailbox has none (the graph keys organizations by domain)
                "website": "" if a.get("domain") in ("", "gmail.com") else a.get("domain", ""),
                **(
                    {"commodity": a.get("commodity", "")}
                    if t == "supplier"
                    else {"industry": a.get("industry", "")}
                ),
                "status": "active",
            }
            people = [
                p
                for p in m.by_type.get("external_person", [])
                if p["relations"].get("employer") == e["id"]
            ]
            if people:
                p = people[0]
                common["primary_contact"], common["contact_email"] = (
                    p["name"],
                    p["attributes"]["email"],
                )
            notes_bits = []
            if a.get("former_name"):
                notes_bits.append(
                    f"Formerly {a['former_name']} (changed {a['rename_effective']})."
                )
            if a.get("domain") == "gmail.com":
                notes_bits.append("Contact uses a personal gmail address.")
            parent = e["relations"].get("parent")
            if parent and parent in m.by_id:
                notes_bits.append(f"Subsidiary of {m.by_id[parent]['name']}.")
            # legacy record
            legacy_date = WINDOW_START - timedelta(days=rng.randrange(30, 2000))
            doc = {
                **common,
                "record_id": legacy,
                "record_date": legacy_date.isoformat(),
                "system": "legacy",
                "legacy_id": legacy,
                "new_id": new,
                "notes": " ".join(notes_bits) or "—",
                REFS_KEY: [_ref(e, _erp_form(e, "legacy"))],
            }
            if a.get("former_name") and _d(a["rename_effective"]) > GO_LIVE:
                doc["legal_name"] = (
                    a["former_name"].upper() if t == "supplier" else a["former_name"]
                )
            people_refs = [_ref(p, p["name"]) for p in people[:1]]
            doc[REFS_KEY] += people_refs
            if _write(f"erp/{folder}/{legacy}.json", doc, "legal_name", ["notes"]):
                written[folder] += 1
            if new:
                new_date = GO_LIVE + timedelta(days=rng.randrange(0, 30))
                doc2 = {
                    **common,
                    "record_id": new,
                    "record_date": new_date.isoformat(),
                    "system": "new_erp",
                    "display_name": _erp_form(e, "new_erp"),
                    "legacy_id": legacy,
                    "new_id": new,
                    "notes": (
                        " ".join(notes_bits + [f"Migrated from legacy {legacy}."])
                    ),
                    REFS_KEY: [_ref(e, _erp_form(e, "new_erp"))] + people_refs,
                }
                if _write(f"erp/{folder}/{new}.json", doc2, "legal_name", ["notes"]):
                    written[folder] += 1

    # ── items ────────────────────────────────────────────────────────────────
    for p in m.by_type.get("part", []):
        a = p["attributes"]
        v = m.by_id.get(p["relations"].get("primary_vendor", ""))
        created = WINDOW_START - timedelta(days=rng.randrange(0, 1500))
        doc = {
            "record_type": "item",
            "record_id": f"{a['item_number']}-{a['revision']}",
            "record_date": created.isoformat(),
            "system": "legacy" if created < GO_LIVE else "new_erp",
            "status": "obsolete" if a.get("obsolete") == "yes" else "active",
            "item_number": a["item_number"],
            "revision": a["revision"],
            "item": f"{a['item_number']} rev {a['revision']}",
            "description": a["description"],
            "supplier_part_number": a.get("previous_supplier_part_number")
            or a["supplier_part_number"],
            "primary_vendor_id": v["attributes"]["legacy_id"] if v else "",
            "primary_vendor_name": _erp_form(v, "legacy") if v else "",
            "supersedes": "",
            "superseded_by": (
                f"{a['item_number']}-{a['superseded_by_revision']}"
                if a.get("superseded_by_revision")
                else ""
            ),
            "unit_cost": a["unit_cost"],
            "obsolete": a.get("obsolete", "no"),
            "notes": (
                f"Rev {a['revision']} superseded by rev {a['superseded_by_revision']} effective {a['supersession_effective']}; supplier P/N changes to {a['supplier_part_number']}."
                if a.get("superseded_by_revision")
                else (
                    f"End of life {a['end_of_life']}." if a.get("end_of_life") else "—"
                )
            ),
            REFS_KEY: [_ref(p, f"{a['item_number']} rev {a['revision']}")]
            + ([_ref(v, _erp_form(v, "legacy"))] if v else []),
        }
        if _write(
            f"erp/items/{a['item_number']}-{a['revision']}.json",
            doc,
            "description",
            ["notes"],
        ):
            written["items"] += 1
        if a.get("superseded_by_revision"):
            nr = a["superseded_by_revision"]
            doc2 = {
                **doc,
                "record_id": f"{a['item_number']}-{nr}",
                "revision": nr,
                "item": f"{a['item_number']} rev {nr}",
                "record_date": a["supersession_effective"],
                "system": (
                    "new_erp"
                    if _d(a["supersession_effective"]) >= GO_LIVE
                    else "legacy"
                ),
                "supplier_part_number": a["supplier_part_number"],
                "supersedes": f"{a['item_number']}-{a['revision']}",
                "superseded_by": "",
                "status": "active",
                "obsolete": "no",
                "notes": f"Supersedes rev {a['revision']} effective {a['supersession_effective']} (ECO).",
                REFS_KEY: [_ref(p, f"{a['item_number']} rev {nr}")]
                + ([_ref(v, _erp_form(v, "legacy"))] if v else []),
            }
            if _write(
                f"erp/items/{a['item_number']}-{nr}.json",
                doc2,
                "description",
                ["notes"],
            ):
                written["items"] += 1

    # ── purchase orders (+ shipments, invoices) ─────────────────────────────
    ship_n, inv_n = 10000, 20000
    for po in m.by_type.get("purchase_order", []):
        a = po["attributes"]
        v = m.by_id[po["relations"]["vendor"]]
        system = a["system"]
        vform = _erp_form(v, system)
        lines, refs = [], [_ref(po, a["po_number"]), _ref(v, vform)]
        total = 0.0
        need = _d(a["promised_date_original"])
        for i, pid in enumerate(po["relations"].get("lines", []), start=1):
            p = m.by_id.get(pid)
            if not p:
                continue
            pa = p["attributes"]
            qty = rng.randrange(1, 40)
            price = float(pa["unit_cost"]) * rng.uniform(0.95, 1.1)
            total += qty * price
            form = f"{pa['item_number']} rev {pa['revision']}"
            lines.append(
                f"line {i}: {form}, {pa['description']}, qty {qty}, unit price {price:.2f}, need date {need.isoformat()}"
            )
            refs.append(_ref(p, form))
        doc = {
            "record_type": "purchase_order",
            "record_id": a["po_number"],
            "record_date": a["order_date"],
            "system": system,
            "status": a["status"],
            "vendor_id": (
                v["attributes"]["new_id"]
                if system == "new_erp" and v["attributes"].get("new_id")
                else v["attributes"]["legacy_id"]
            ),
            "vendor_name": vform,
            "buyer": a["buyer"],
            "order_date": a["order_date"],
            "promised_date": a["promised_date_current"],
            "promised_date_history": a["promised_date_history"] or ["—"],
            "ship_to": a["ship_to"],
            "machine_job": a.get("machine_job", "") or "",
            "lines": lines,
            "total": f"{total:.2f}",
            "notes": (
                "Migrated open PO; promised dates re-entered at cutover."
                if _d(a["order_date"]) < GO_LIVE
                and _d(a["promised_date_current"]) > GO_LIVE
                else "—"
            ),
            REFS_KEY: refs,
        }
        if _write(
            f"erp/purchase_orders/{a['po_number']}.json",
            doc,
            "record_id",
            ["lines", "promised_date_history", "notes"],
        ):
            written["purchase_orders"] += 1
        # shipments and invoices
        if a["status"] in ("received", "partial", "closed"):
            n_ship = 2 if a["status"] == "partial" or rng.random() < 0.4 else 1
            for k in range(n_ship):
                ship_n += rng.randrange(1, 4)
                sd = _d(a["promised_date_current"]) + timedelta(
                    days=rng.randrange(-3, 12) + 10 * k
                )
                if sd > WINDOW_END:
                    break
                carrier = rng.choice(carriers) if carriers else None
                damage = rng.random() < 0.06
                sid = f"SHP-{sd.strftime('%y')}-{ship_n:05d}"
                sdoc = {
                    "record_type": "shipment",
                    "record_id": sid,
                    "record_date": sd.isoformat(),
                    "system": "legacy" if sd < GO_LIVE else "new_erp",
                    "status": (
                        "delivered"
                        if sd + timedelta(days=5) < WINDOW_END
                        else "in transit"
                    ),
                    "reference": a["po_number"],
                    "vendor_name": vform,
                    "carrier": (
                        _erp_form(carrier, "legacy") if carrier else "vendor truck"
                    ),
                    "ship_date": sd.isoformat(),
                    "delivered_date": (
                        sd + timedelta(days=rng.randrange(1, 8))
                    ).isoformat(),
                    "tracking": f"{rng.randrange(10**9, 10**10 - 1)}",
                    "damage_reported": "yes" if damage else "no",
                    "notes": (
                        "Damage noted at receiving; claim opened with carrier."
                        if damage
                        else (
                            f"Partial shipment {k + 1} of {n_ship}."
                            if n_ship > 1
                            else "—"
                        )
                    ),
                    REFS_KEY: [_ref(po, a["po_number"]), _ref(v, vform)]
                    + (
                        [_ref(carrier, _erp_form(carrier, "legacy"))] if carrier else []
                    ),
                }
                if _write(f"erp/shipments/{sid}.json", sdoc, "record_id", ["notes"]):
                    written["shipments"] += 1
        if a["status"] != "cancelled":
            n_inv = 2 if rng.random() < 0.3 else 1
            for k in range(n_inv):
                inv_n += rng.randrange(1, 5)
                idt = _d(a["promised_date_current"]) + timedelta(
                    days=rng.randrange(0, 20) + 15 * k
                )
                if idt > WINDOW_END:
                    break
                iid = f"INV-{idt.strftime('%Y')}-{inv_n:05d}"
                amount = total / n_inv
                dispute = rng.random() < 0.08
                idoc = {
                    "record_type": "invoice",
                    "record_id": iid,
                    "record_date": idt.isoformat(),
                    "system": "legacy" if idt < GO_LIVE else "new_erp",
                    "status": (
                        "disputed" if dispute else rng.choice(["paid", "paid", "open"])
                    ),
                    "reference": a["po_number"],
                    "vendor_or_customer": vform,
                    "invoice_date": idt.isoformat(),
                    "due_date": (idt + timedelta(days=30)).isoformat(),
                    "amount": f"{amount:.2f}",
                    "paid_date": (
                        (idt + timedelta(days=rng.randrange(20, 50))).isoformat()
                        if not dispute
                        else ""
                    ),
                    "dispute_notes": (
                        rng.choice(
                            [
                                "Freight charges billed twice.",
                                "Quantity invoiced exceeds quantity received.",
                                "Price differs from PO line.",
                                "Invoice references a cancelled line.",
                            ]
                        )
                        if dispute
                        else "—"
                    ),
                    REFS_KEY: [_ref(po, a["po_number"]), _ref(v, vform)],
                }
                if _write(
                    f"erp/invoices/{iid}.json", idoc, "record_id", ["dispute_notes"]
                ):
                    written["invoices"] += 1

    # ── sales orders (+ shipments, invoices) ────────────────────────────────
    for so in m.by_type.get("sales_order", []):
        a = so["attributes"]
        c = m.by_id[so["relations"]["customer"]]
        site = m.by_id.get(so["relations"].get("site", ""))
        q = m.by_id.get(so["relations"].get("quote", ""))
        system = a["system"]
        cform = _erp_form(c, system)
        amount = float(a["amount_usd"])
        lines = [
            f"line 1: {a['machine_type']}, per quote {q['attributes']['quote_number'] if q else 'n/a'}, qty 1, price {amount:.2f}"
        ]
        refs = [_ref(so, a["so_number"]), _ref(so, a["machine_job"]), _ref(c, cform)]
        if site:
            refs.append(_ref(site, site["name"]))
        if q:
            refs.append(_ref(q, q["attributes"]["quote_number"]))
        doc = {
            "record_type": "sales_order",
            "record_id": a["so_number"],
            "record_date": a["order_date"],
            "system": system,
            "status": (
                "shipped"
                if _d(a["current_ship_date"]) < WINDOW_END - timedelta(days=15)
                else "open"
            ),
            "customer_id": (
                c["attributes"]["new_id"]
                if system == "new_erp" and c["attributes"].get("new_id")
                else c["attributes"]["legacy_id"]
            ),
            "customer_name": cform,
            "customer_site": site["name"] if site else "",
            "machine_job": a["machine_job"],
            "order_date": a["order_date"],
            "requested_ship_date": a["requested_ship_date"],
            "current_ship_date": a["current_ship_date"],
            "ship_date_history": a["ship_date_history"] or ["—"],
            "lines": lines,
            "total": f"{amount:.2f}",
            "project_manager": a["project_manager"],
            "build_site": a["build_site"],
            "notes": "—",
            REFS_KEY: refs,
        }
        if _write(
            f"erp/sales_orders/{a['so_number']}.json",
            doc,
            "record_id",
            ["lines", "ship_date_history", "notes"],
        ):
            written["sales_orders"] += 1
        sd = _d(a["current_ship_date"])
        if sd < WINDOW_END - timedelta(days=15):
            ship_n += rng.randrange(1, 4)
            carrier = rng.choice(carriers) if carriers else None
            sid = f"SHP-{sd.strftime('%y')}-{ship_n:05d}"
            damage = rng.random() < 0.05
            sdoc = {
                "record_type": "shipment",
                "record_id": sid,
                "record_date": sd.isoformat(),
                "system": "legacy" if sd < GO_LIVE else "new_erp",
                "status": "delivered",
                "reference": a["so_number"],
                "machine_job": a["machine_job"],
                "customer_name": cform,
                "ship_to": site["name"] if site else cform,
                "carrier": (
                    _erp_form(carrier, "legacy") if carrier else "customer pickup"
                ),
                "ship_date": sd.isoformat(),
                "delivered_date": (
                    sd + timedelta(days=rng.randrange(2, 9))
                ).isoformat(),
                "tracking": f"{rng.randrange(10**9, 10**10 - 1)}",
                "damage_reported": "yes" if damage else "no",
                "notes": (
                    "Crate damage reported at customer dock; claim filed."
                    if damage
                    else f"Machine job {a['machine_job']} shipped from {a['build_site']}."
                ),
                REFS_KEY: [
                    _ref(so, a["so_number"]),
                    _ref(so, a["machine_job"]),
                    _ref(c, cform),
                ]
                + ([_ref(carrier, _erp_form(carrier, "legacy"))] if carrier else []),
            }
            if _write(f"erp/shipments/{sid}.json", sdoc, "record_id", ["notes"]):
                written["shipments"] += 1
        for k, (label, share, when) in enumerate(
            (
                ("deposit", 0.5, _d(a["order_date"]) + timedelta(days=5)),
                ("final", 0.5, sd + timedelta(days=rng.randrange(1, 10))),
            )
        ):
            if when > WINDOW_END:
                break
            inv_n += rng.randrange(1, 5)
            iid = f"INV-{when.strftime('%Y')}-{inv_n:05d}"
            idoc = {
                "record_type": "invoice",
                "record_id": iid,
                "record_date": when.isoformat(),
                "system": "legacy" if when < GO_LIVE else "new_erp",
                "status": rng.choice(["paid", "paid", "open"]),
                "reference": a["so_number"],
                "vendor_or_customer": cform,
                "invoice_date": when.isoformat(),
                "due_date": (when + timedelta(days=30)).isoformat(),
                "amount": f"{amount * share:.2f}",
                "paid_date": (when + timedelta(days=rng.randrange(15, 60))).isoformat(),
                "dispute_notes": f"{label} invoice for machine job {a['machine_job']}.",
                REFS_KEY: [
                    _ref(so, a["so_number"]),
                    _ref(so, a["machine_job"]),
                    _ref(c, cform),
                ],
            }
            if _write(f"erp/invoices/{iid}.json", idoc, "record_id", ["dispute_notes"]):
                written["invoices"] += 1
    print(written, "total", sum(written.values()))


if __name__ == "__main__":
    main()

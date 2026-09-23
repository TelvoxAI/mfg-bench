"""Render the HubSpot company, contact and deal records from the entity master (IND-982).

CRM records are structured and maintained by Sales, so they are rendered from the master
the way ERP records are: every customer becomes a company record, every external person
at a customer a contact, every quote a deal. HubSpot's alias convention (a short record
name, sometimes stale, sometimes an old name) is applied here, and `_entity_refs` are
exact by construction. The free-text `notes/` folder is left to step 9 (model-written
call notes), which is where the informal mentions come from.

Staleness, deliberately: a renamed customer keeps its OLD name in HubSpot (nobody
updated the record); a contact who changed employers keeps a record at the old company
too; deals that became sales orders are sometimes still in "quote sent".

Idempotent; sets field labels and dataset uuids without a model call.

Usage:
    python -m src.scripts.util_scripts.build_hubspot_records [--seed 20260922]
"""

from __future__ import annotations

import argparse
import os
import random
from datetime import date, timedelta

from src.entities.master import REFS_KEY, SEP, load_master, surface_forms
from src.paths import SOURCES_DIR
from src.utils.dataset_id import add_dataset_doc_uuid
from src.utils.file_io import sanitize_filename, write_json_file

WINDOW_START = date(2025, 4, 1)
WINDOW_END = date(2026, 9, 30)


def _ref(e: dict, form: str) -> str:
    return f"{e['id']}{SEP}{form}"


def _write(rel: str, doc: dict, title_field: str, content_fields: list[str]) -> bool:
    path = os.path.join(SOURCES_DIR, rel)
    if os.path.exists(path):
        return False
    doc["title_field_name"] = title_field
    doc["content_field_names"] = content_fields
    write_json_file(path, doc)
    add_dataset_doc_uuid(path)
    return True


def _hub_name(c: dict) -> str:
    """The CRM record name: the trade name, or the OLD name for a renamed customer
    (HubSpot is stale), which is the first hubspot alias after the trade name."""
    a = c["attributes"]
    if a.get("former_name"):
        forms = surface_forms(c, "hubspot")
        return forms[1] if len(forms) > 1 else forms[0]
    return surface_forms(c, "hubspot")[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260922)
    args = ap.parse_args()
    rng = random.Random(args.seed + 1)
    m = load_master()
    if m is None:
        raise SystemExit("entity master not found (ENTITY_MASTER_PATH)")
    written = {"companies": 0, "contacts": 0, "deals": 0}
    owners = sorted({q["attributes"]["owner"] for q in m.by_type.get("quote", [])})
    rec_id = 5000
    customers = m.by_type.get("customer", [])
    sites_by_c: dict[str, list[dict]] = {}
    for s in m.by_type.get("customer_site", []):
        sites_by_c.setdefault(s["relations"]["customer"], []).append(s)
    people_by_c: dict[str, list[dict]] = {}
    for p in m.by_type.get("external_person", []):
        people_by_c.setdefault(p["relations"]["employer"], []).append(p)
        if p["relations"].get("former_employer"):
            people_by_c.setdefault(p["relations"]["former_employer"], []).append(p)

    for c in customers:
        a = c["attributes"]
        rec_id += rng.randrange(1, 9)
        name = _hub_name(c)
        created = WINDOW_START - timedelta(days=rng.randrange(30, 1800))
        modified = created + timedelta(
            days=rng.randrange(0, (WINDOW_END - created).days)
        )
        sites = sites_by_c.get(c["id"], [])
        doc = {
            "object_type": "company",
            "record_id": str(rec_id),
            "created_at": created.isoformat(),
            "last_modified": modified.isoformat(),
            "owner": rng.choice(owners),
            "name": name,
            "domain": a["domain"],
            "industry": a.get("industry", ""),
            "plant_locations": [
                f"{s['attributes']['city']}, {s['attributes']['state']}" for s in sites
            ]
            or ["—"],
            "lifecycle_stage": rng.choice(
                ["customer", "customer", "customer", "opportunity"]
            ),
            "description": f"{name} — {a.get('industry', '')} manufacturer, HQ {a.get('hq_city', '')}, {a.get('hq_state', '')}. "
            + rng.choice(
                [
                    "Long-standing account.",
                    "Installed base: two lines.",
                    "Prospect converted last year.",
                    "Buys retrofits mostly.",
                    "Key account for the beverage retrofit program.",
                ]
            ),
            REFS_KEY: [_ref(c, name)],
        }
        if _write(
            f"hubspot/companies/{sanitize_filename(name.lower().replace(' ', '-'))}.json",
            doc,
            "name",
            ["description", "plant_locations"],
        ):
            written["companies"] += 1

        for p in people_by_c.get(c["id"], []):
            pa = p["attributes"]
            rec_id += rng.randrange(1, 9)
            is_former = p["relations"].get("former_employer") == c["id"]
            created = WINDOW_START - timedelta(days=rng.randrange(0, 1200))
            email = (
                pa.get("former_email")
                if is_former and pa.get("former_email")
                else pa["email"]
            )
            doc = {
                "object_type": "contact",
                "record_id": str(rec_id),
                "created_at": created.isoformat(),
                "last_modified": (
                    created + timedelta(days=rng.randrange(0, 300))
                ).isoformat(),
                "owner": rng.choice(owners),
                "full_name": p["name"],
                "first_name": pa["first_name"],
                "last_name": pa["last_name"],
                "email": email,
                "phone": pa.get("phone", ""),
                "job_title": pa["title"],
                "company_name": name,
                "previous_company": "",
                "notes": (
                    "Left the company — record not updated."
                    if is_former
                    else rng.choice(
                        [
                            "Main technical contact.",
                            "Signs off on FAT.",
                            "Handles POs and spec changes.",
                            "Met at the plant walk-through.",
                            "Prefers phone over email.",
                        ]
                    )
                ),
                REFS_KEY: [_ref(p, p["name"]), _ref(c, name)],
            }
            if not is_former and p["relations"].get("former_employer") in m.by_id:
                old = m.by_id[p["relations"]["former_employer"]]
                doc["previous_company"] = (
                    _hub_name(old) if old["type"] == "customer" else old["name"]
                )
                doc["notes"] = (
                    f"Moved here from {doc['previous_company']} ({pa.get('employer_change_effective', '')})."
                )
            fn = sanitize_filename(
                f"{pa['first_name']}-{pa['last_name']}".lower()
                + ("-former" if is_former else "")
            )
            if _write(f"hubspot/contacts/{fn}.json", doc, "last_name", ["notes"]):
                written["contacts"] += 1

    for q in m.by_type.get("quote", []):
        a = q["attributes"]
        c = m.by_id[q["relations"]["customer"]]
        site = m.by_id.get(q["relations"].get("site", ""))
        name = _hub_name(c)
        rec_id += rng.randrange(1, 9)
        deal_name = f"{name} - {a['machine_type']} - {site['attributes']['city'] if site else c['attributes'].get('hq_city', '')}"
        won = a["status"] == "won"
        stage = (
            "closed won"
            if won and rng.random() < 0.8
            else (
                "quote sent"
                if won
                else {
                    "open": "quote sent",
                    "lost": "closed lost",
                    "no decision": "stalled",
                }.get(a["status"], "quote sent")
            )
        )
        contacts = [p["name"] for p in people_by_c.get(c["id"], [])][:2]
        qdate = date.fromisoformat(a["date"])
        doc = {
            "object_type": "deal",
            "record_id": str(rec_id),
            "created_at": (qdate - timedelta(days=rng.randrange(5, 60))).isoformat(),
            "last_modified": min(
                qdate + timedelta(days=rng.randrange(0, 120)), WINDOW_END
            ).isoformat(),
            "owner": a["owner"],
            "deal_name": deal_name,
            "stage": stage,
            "amount": a["amount_usd"],
            "close_date": min(
                qdate + timedelta(days=rng.randrange(30, 150)), WINDOW_END
            ).isoformat(),
            "company_name": name,
            "contacts": contacts or ["—"],
            "machine_type": a["machine_type"],
            "description": f"{a['machine_type']} opportunity, quote {a['quote_number']} (RFQ {a['rfq_number']}) sent {a['date']}."
            + (" PO received." if won else "")
            + (f" Site: {site['attributes']['city']} plant." if site else ""),
            REFS_KEY: [
                _ref(q, a["quote_number"]),
                _ref(q, a["rfq_number"]),
                _ref(c, name),
            ]
            + [_ref(p, p["name"]) for p in people_by_c.get(c["id"], [])[:2]]
            + ([_ref(site, f"{site['attributes']['city']} plant")] if site else []),
        }
        fn = sanitize_filename(deal_name.lower().replace(" - ", "-").replace(" ", "-"))
        if _write(
            f"hubspot/deals/{fn}-{a['quote_number'].lower()}.json",
            doc,
            "deal_name",
            ["description", "contacts"],
        ):
            written["deals"] += 1
    print(written, "total", sum(written.values()))


if __name__ == "__main__":
    main()

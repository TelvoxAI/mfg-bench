"""Attach a consistent entity set to a project (IND-982, code change C2).

Step 6 enriches ~60 projects with ~100 planned documents each. Without an anchor, every
document of a project would draw its own random counterparties and the project would
not read as one story. This module picks, per project, the customers and suppliers that
fit its description (cheap model, from a popularity-weighted candidate list) and then
attaches deterministically the people at those companies, the purchase orders to those
suppliers, the sales orders / quotes / sites of those customers.

The result is stored under `entities` in the project JSON as `[{id, type, name, role}]`.
The ids are internal: step 7 removes the field from the project JSON before the model
sees it and hands the same entities over through the shortlist by local key.
"""

from __future__ import annotations

import json
import random

from src.entities.master import Master, _popularity
from src.llm import get_cheap_llm
from src.llm.interface import Message
from src.utils import extract_json_from_response, load_json_file, write_json_file

PICK_PROMPT = """
You are helping plan a realistic corpus of documents for a company project. Below is the project and a list of
candidate counterparties (customers and suppliers of the company). Pick the ones that would realistically be
involved in this project: 2-5 customers and 2-5 suppliers when both make sense, fewer when the project is
internal (an IT or HR project may involve one supplier and no customers). Give each a one-line role in the project.

## Project
{project}

## Candidates
{candidates}

Output ONLY a JSON object: {{"picks": [{{"key": "C3", "role": "..."}}, ...]}}. Keys must come from the candidate list.
""".strip()


def _candidates(master: Master, seed: str) -> list[tuple[str, dict]]:
    rng = random.Random(f"project-candidates|{seed}")
    pop = _popularity(master)

    def weighted(pool: list[dict], n: int) -> list[dict]:
        cand, cw, out = list(pool), [pop.get(e["id"], 1.0) for e in pool], []
        for _ in range(min(n, len(cand))):
            i = rng.choices(range(len(cand)), weights=cw, k=1)[0]
            out.append(cand.pop(i))
            cw.pop(i)
        return out

    cands = weighted(master.by_type.get("customer", []), 12) + weighted(
        master.by_type.get("supplier", []), 12
    )
    return [(f"C{i + 1}", e) for i, e in enumerate(cands)]


def _line(key: str, e: dict) -> str:
    a = e["attributes"]
    if e["type"] == "customer":
        return f"[{key}] {e['name']} — customer, {a.get('industry')}, {a.get('hq_city')} {a.get('hq_state')}"
    return f"[{key}] {e['name']} — supplier of {a.get('commodity')}, {a.get('hq_city')} {a.get('hq_state')}, {a.get('size')}"


def attach_entities_to_project(
    project_path: str, master: Master, quiet: bool = True
) -> int:
    project = load_json_file(project_path)
    if project.get("entities"):
        return len(project["entities"])
    seed = project_path.rsplit("/", 1)[-1]
    cands = _candidates(master, seed)
    prompt = PICK_PROMPT.format(
        project=json.dumps(
            {k: project[k] for k in ("name", "description") if k in project}, indent=1
        )[:4000],
        candidates="\n".join(_line(k, e) for k, e in cands),
    )
    llm = get_cheap_llm(quiet=quiet)
    response = "".join(
        c
        for c in llm.generate([Message(role="user", content=prompt)])
        if isinstance(c, str)
    )
    picks = json.loads(extract_json_from_response(response)).get("picks", [])
    by_key = dict(cands)
    chosen: dict[str, dict] = {}
    for p in picks:
        e = by_key.get(str(p.get("key", "")).strip("[]"))
        if e is not None and e["id"] not in chosen:
            chosen[e["id"]] = {
                "id": e["id"],
                "type": e["type"],
                "name": e["name"],
                "role": str(p.get("role", ""))[:200],
            }
    # The project text names counterparties the planner invented ("Harbor Peak Pharma").
    # Map each invented name onto a picked entity and rewrite the project (name,
    # description, file descriptions) so every document of the project talks about the
    # same real entities. Unmapped names are kept as they are.
    if chosen:
        project = _rewrite_invented_names(project, chosen, llm)
    if not chosen:  # the model picked nothing usable: take the two most popular of each
        for k, e in cands[:2] + cands[12:14]:
            chosen[e["id"]] = {
                "id": e["id"],
                "type": e["type"],
                "name": e["name"],
                "role": "counterparty",
            }
    # deterministic attachments: people, POs, SOs, quotes, sites of the chosen companies
    rng = random.Random(f"project-attach|{seed}")
    company_ids = set(chosen)
    for t, rel, per in (
        ("external_person", "employer", 2),
        ("purchase_order", "vendor", 2),
        ("sales_order", "customer", 2),
        ("quote", "customer", 2),
        ("customer_site", "customer", 1),
    ):
        for cid in list(company_ids):
            linked = [
                e
                for e in master.by_type.get(t, [])
                if e.get("relations", {}).get(rel) == cid
            ]
            for e in rng.sample(linked, min(per, len(linked))):
                chosen.setdefault(
                    e["id"],
                    {
                        "id": e["id"],
                        "type": e["type"],
                        "name": e["name"],
                        "role": f"{t.replace('_', ' ')} of {master.by_id[cid]['name']}",
                    },
                )
    # parts on the attached POs
    for e in [x for x in chosen.values() if x["type"] == "purchase_order"]:
        for pid in master.by_id[e["id"]].get("relations", {}).get("lines", [])[:2]:
            p = master.by_id.get(pid)
            if p:
                chosen.setdefault(
                    p["id"],
                    {
                        "id": p["id"],
                        "type": "part",
                        "name": p["name"],
                        "role": "part on an attached PO",
                    },
                )
    project["entities"] = list(chosen.values())[:40]
    write_json_file(project_path, project)
    return len(project["entities"])


RENAME_PROMPT = """
Below is a project plan for a company and the list of real counterparties chosen for it. The plan was written
before the counterparties were chosen, so it may name invented customers or suppliers. For every invented
company name that appears in the plan (project name, description, file descriptions), say which chosen
counterparty it should become. Match by role (the main customer of the plan -> the chosen customer with the
customer role, a machining supplier -> the chosen machining supplier). Only map names that are clearly a
company; leave people, parts and places alone. If nothing needs mapping, return an empty object.

## Chosen counterparties
{chosen}

## Plan
{plan}

Output ONLY a JSON object: {{"replacements": {{"Invented Name As Written": "K3", ...}}}} where the value is the key
of the chosen counterparty.
""".strip()


def _rewrite_invented_names(project: dict, chosen: dict[str, dict], llm) -> dict:
    keys = {f"K{i + 1}": e for i, e in enumerate(chosen.values())}
    plan_text = json.dumps(
        {
            "name": project.get("name", ""),
            "description": project.get("description", ""),
            "files": [f.get("description", "") for f in project.get("files", [])][:60],
        },
        ensure_ascii=False,
    )[:12000]
    prompt = RENAME_PROMPT.format(
        chosen="\n".join(
            f"[{k}] {e['name']} — {e['type']}: {e['role']}" for k, e in keys.items()
        ),
        plan=plan_text,
    )
    try:
        resp = "".join(
            c
            for c in llm.generate([Message(role="user", content=prompt)])
            if isinstance(c, str)
        )
        mapping = (
            json.loads(extract_json_from_response(resp)).get("replacements", {}) or {}
        )
    except Exception:
        return project
    repl: dict[str, str] = {}
    for invented, key in mapping.items():
        e = keys.get(str(key).strip("[]"))
        invented = str(invented).strip()
        if (
            e
            and invented
            and len(invented) > 3
            and invented.lower() != e["name"].lower()
        ):
            repl[invented] = e["name"]
    if not repl:
        return project

    def sub(text: str) -> str:
        for a, b in sorted(repl.items(), key=lambda kv: -len(kv[0])):
            text = text.replace(a, b)
        return text

    for k in ("name", "description"):
        if isinstance(project.get(k), str):
            project[k] = sub(project[k])
    for f in project.get("files", []):
        if isinstance(f.get("description"), str):
            f["description"] = sub(f["description"])
    project["entity_renames"] = repl
    return project

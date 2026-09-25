"""Templated noise mail for the outlook source (no LLM, deterministic).

A real mailbox is mostly not business correspondence: newsletters, system notifications,
calendar and file-share notices, out-of-office replies, carrier tracking, company
broadcasts and spam. A benchmark with only business mail flatters every retrieval method,
and it never exercises the part of an ingestion pipeline that has to throw mail away.
This step adds that mail, in the same flat JSON as the business emails, to the mailbox
folders of the employee directory. Every sender is fictional; no document mentions a
gold entity, so the ER gold and the questions are unaffected.

Run:
    python -m src.scripts.data_gen_stage_2_add_noise.step_5_generate_noise_mail --count 15000
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import uuid
from datetime import datetime, timedelta

import yaml

from src.paths import EMPLOYEE_DIRECTORY_PATH, SOURCES_DIR

WINDOW_START = datetime(2025, 4, 1, 6, 0)
WINDOW_END = datetime(2026, 9, 30, 20, 0)
DOMAIN = "brightwaterpkg.com"

# share of the noise mail per kind
MIX = {
    "newsletter": 0.28, "system": 0.22, "calendar": 0.10, "file_share": 0.07,
    "out_of_office": 0.07, "carrier": 0.05, "broadcast": 0.09, "spam": 0.09, "security": 0.03,
}

NEWSLETTERS = [
    ("PackLine Weekly", "news@packlineweekly-mail.com", ["Five trends reshaping end-of-line automation",
     "Inside a 400-cpm beverage retrofit", "Servo sizing mistakes that cost you uptime",
     "Changeover in under 10 minutes: what it takes", "Labor shortages and the case for cobots"]),
    ("Automation Insider", "digest@automationinsider-news.com", ["Weekly digest: motion control",
     "PLC migration checklists for 2026", "Safety standards update: what changed",
     "Vision inspection on a budget", "The state of industrial networking"]),
    ("Midwest Manufacturers Council", "events@mwmfgcouncil.org", ["Member breakfast: supply chain outlook",
     "Workforce grant deadline approaching", "Plant tour registration now open",
     "Quarterly economic briefing", "Apprenticeship program: call for mentors"]),
    ("FabShop Supply Deals", "offers@fabshopsupply-deals.com", ["Clearance: abrasives and cutting fluids",
     "20% off safety glasses this week", "New arrivals: torque tools", "Free shipping over $250",
     "Your cart is waiting"]),
    ("Ohio Valley Business Journal", "newsletter@ovbj-daily.com", ["Morning briefing", "Dayton region jobs report",
     "Local manufacturers expand hiring", "Weekend edition", "Commercial real estate roundup"]),
    ("Controls Academy", "learn@controls-academy.io", ["New course: structured text for beginners",
     "Webinar tomorrow: diagnosing drive faults", "Certificate reminder", "Your weekly learning plan",
     "Recording available"]),
]
SYSTEMS = [
    ("ERP Notifications", f"erp-noreply@{DOMAIN}", ["Scheduled report ready: open POs by buyer",
     "Nightly MRP run completed", "Job costing export finished", "Approval workflow: 3 items waiting",
     "Batch posting completed with 0 errors"]),
    ("CRM Digest", f"crm-noreply@{DOMAIN}", ["Your weekly pipeline summary", "Tasks due this week",
     "Daily activity digest", "Sequence report", "Meeting reminders for tomorrow"]),
    ("IT Helpdesk", f"helpdesk@{DOMAIN}", ["Ticket #{n} has been resolved", "Ticket #{n} received",
     "Scheduled maintenance this Saturday", "Your password expires in 7 days", "Printer queue restored"]),
    ("Expense System", f"expenses-noreply@{DOMAIN}", ["Expense report approved", "Receipt missing on report #{n}",
     "Monthly card statement available", "Reminder: submit mileage", "Report #{n} returned for changes"]),
    ("Timesheets", f"timesheets@{DOMAIN}", ["Timesheet due Friday", "Timesheet approved", "Missing hours for last week",
     "Overtime pre-approval needed", "Holiday calendar updated"]),
]
CARRIERS = [("Great Lakes Freight Tracking", "tracking@glf-tracking.com"),
            ("ParcelNow Notifications", "notify@parcelnow-ship.com"),
            ("Summit LTL Updates", "updates@summitltl-mail.com")]
SPAM = [
    ("Account Security Team", "security@acct-verify-center.net", "Action required: verify your mailbox"),
    ("Invoice Dept", "billing@secure-invoicing-portal.co", "Overdue invoice attached - please review"),
    ("Global Leads", "sales@b2b-leads-direct.biz", "10,000 verified plant-manager contacts"),
    ("Freight Quotes", "quotes@cheapest-freight-now.info", "Lowest LTL rates guaranteed"),
    ("SEO Experts", "hello@rank1-seo-growth.com", "Your website is losing customers"),
    ("Shared Document", "docs@file-share-secure.org", "You have received a shared document"),
    ("Prize Center", "winner@customer-rewards-center.net", "Congratulations, you have been selected"),
]
BROADCASTS = [
    ("All-hands meeting Thursday 3 pm in the shop", "Please join us Thursday at 3 pm by the assembly bay for the monthly all-hands. We will cover bookings, safety and the plant schedule. Pizza after."),
    ("Benefits open enrollment", "Open enrollment runs through the end of the month. Please review your elections in the benefits portal and reach out with questions."),
    ("Parking lot resurfacing Saturday", "The east lot will be closed Saturday for resurfacing. Please use the north lot."),
    ("Food truck Friday", "A food truck will be in the lot Friday from 11:30 to 1:00."),
    ("Safety reminder: forklift traffic", "Please stay inside the marked walkways near shipping. Forklift traffic is heavy this week."),
    ("Office closed for the holiday", "The office will be closed Monday for the holiday. Field service on-call rotation is posted."),
    ("Welcome our new team members", "Please welcome the colleagues who joined us this month. Stop by and say hello."),
    ("Quarterly town hall recording", "The recording of the quarterly town hall is on the intranet for anyone who missed it."),
]


def _mailboxes() -> list[dict]:
    with open(EMPLOYEE_DIRECTORY_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    out = []
    for dept, people in (data.get("departments") or {}).items():
        for p in people or []:
            email = str(p.get("email") or "")
            local = email.split("@")[0]
            if local and os.path.isdir(os.path.join(SOURCES_DIR, "outlook", local)):
                out.append({"name": p["name"], "email": email, "local": local, "title": p.get("title", ""),
                            "dept": dept})
    return out


def _when(rng: random.Random) -> datetime:
    span = int((WINDOW_END - WINDOW_START).total_seconds())
    t = WINDOW_START + timedelta(seconds=rng.randrange(span))
    if t.weekday() >= 5 and rng.random() < 0.7:          # most mail lands on weekdays
        t -= timedelta(days=t.weekday() - 4)
    if rng.random() < 0.85:                                # and in office hours, Eastern (UTC-4/5)
        t = t.replace(hour=rng.randrange(11, 23), minute=rng.randrange(0, 60) // 15 * 15)
    return t


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "mail"


def _doc(owner: dict, sender: str, subject: str, body: str, when: datetime, to: list[str] | None = None) -> dict:
    return {"subject": subject, "from": sender, "to": to or [owner["email"]], "cc": [],
            "sent_at": when.strftime("%Y-%m-%dT%H:%M:00Z"), "mailbox": owner["local"],
            "thread_subject": re.sub(r"^(re|fwd?|automatic reply):\s*", "", subject, flags=re.I),
            "body": body, "attachments": []}


def make(kind: str, owner: dict, people: list[dict], rng: random.Random) -> dict:
    when = _when(rng)
    first = owner["name"].split()[0]
    n = rng.randrange(1000, 9999)
    if kind == "newsletter":
        name, addr, subjects = rng.choice(NEWSLETTERS)
        subject = rng.choice(subjects)
        body = (f"{subject}\n\n{name} | {when:%B %d, %Y}\n\nIn this issue:\n- {rng.choice(subjects)}\n"
                f"- {rng.choice(subjects)}\n- Upcoming events and webinars\n\nRead more on our website.\n\n"
                f"You are receiving this email because {owner['email']} subscribed. Unsubscribe | Manage preferences")
        return _doc(owner, f"{name} <{addr}>", subject, body, when)
    if kind == "system":
        name, addr, subjects = rng.choice(SYSTEMS)
        subject = rng.choice(subjects).format(n=n)
        body = (f"Hello {first},\n\n{subject}.\n\nThis is an automated message. Please do not reply.\n\n"
                f"-- {name}")
        return _doc(owner, f"{name} <{addr}>", subject, body, when)
    if kind == "calendar":
        other = rng.choice(people)
        topic = rng.choice(["Weekly staff meeting", "1:1", "Project sync", "Lunch and learn", "Safety committee",
                            "Budget review", "Training: new ERP screens", "Team huddle"])
        verb = rng.choice(["Invitation", "Updated invitation", "Accepted", "Declined", "Canceled"])
        subject = f"{verb}: {topic} @ {when:%a %b %d} {when:%I:%M %p}"
        body = (f"{other['name']} {'has ' + verb.lower() if verb in ('Accepted', 'Declined') else 'invited you to'} "
                f"{topic}.\n\nWhen: {when:%A, %B %d, %Y %I:%M %p} Eastern\nWhere: Conference room / online meeting\n\n"
                "Join online meeting")
        return _doc(owner, f"{other['name']} <{other['email']}>", subject, body, when)
    if kind == "file_share":
        other = rng.choice(people)
        fname = rng.choice(["Weekly schedule.xlsx", "Meeting notes.docx", "Photos from the floor", "Training deck.pptx",
                            "Org chart.pdf", "Holiday calendar.xlsx", "Shop layout.pdf"])
        subject = f"{other['name']} shared \"{fname}\" with you"
        body = f"{other['name']} shared a file with you.\n\n{fname}\n\nOpen\n\nThis email was generated by the file-sharing service."
        return _doc(owner, f"File sharing <no-reply@{DOMAIN}>", subject, body, when)
    if kind == "out_of_office":
        other = rng.choice(people)
        back = when + timedelta(days=rng.randrange(2, 12))
        subject = f"Automatic reply: {rng.choice(['Quick question', 'Following up', 'Schedule', 'Update', 'Checking in'])}"
        body = (f"Thank you for your message. I am out of the office until {back:%A, %B %d} with limited access to email. "
                f"For urgent matters please contact the main office.\n\n{other['name']}\n{other['title']}")
        return _doc(owner, f"{other['name']} <{other['email']}>", subject, body, when)
    if kind == "carrier":
        name, addr = rng.choice(CARRIERS)
        pro = f"{rng.randrange(10**9, 10**10)}"
        status = rng.choice(["Picked up", "In transit", "Out for delivery", "Delivered", "Delivery exception - rescheduled"])
        subject = f"Shipment {pro}: {status}"
        body = (f"Tracking number: {pro}\nStatus: {status}\nUpdated: {when:%m/%d/%Y %I:%M %p}\n\n"
                "Track your shipment online. This is an automated notification; replies are not monitored.")
        return _doc(owner, f"{name} <{addr}>", subject, body, when)
    if kind == "broadcast":
        subject, text = rng.choice(BROADCASTS)
        sender = rng.choice([p for p in people if "HR" in p["dept"] or "Executive" in p["dept"]] or people)
        body = f"Hi all,\n\n{text}\n\nThanks,\n{sender['name']}"
        return _doc(owner, f"{sender['name']} <{sender['email']}>", subject, body, when, to=[f"all@{DOMAIN}"])
    if kind == "security":
        subject = rng.choice(["New sign-in to your account", "Multi-factor authentication method added",
                              "Your mailbox is almost full", "Quarantine summary: 4 messages held"])
        body = f"Hello {first},\n\n{subject}.\n\nIf this was you, no action is needed.\n\nIT Security"
        return _doc(owner, f"IT Security <it-security@{DOMAIN}>", subject, body, when)
    name, addr, subject = rng.choice(SPAM)
    body = (f"Dear {rng.choice([first, 'Customer', 'Sir/Madam', 'Valued Partner'])},\n\n{subject}. "
            "Click the link below within 24 hours to avoid interruption.\n\nhttps://example.invalid/verify\n\n"
            f"Regards,\n{name}")
    return _doc(owner, f"{name} <{addr}>", subject, body, when)


def main() -> None:
    ap = argparse.ArgumentParser(description="Templated noise mail for the outlook source")
    ap.add_argument("--count", type=int, default=15000)
    ap.add_argument("--seed", type=int, default=20260925)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    people = _mailboxes()
    if not people:
        raise SystemExit("no mailbox folders match the employee directory")
    kinds, weights = zip(*MIX.items())
    counts: dict[str, int] = {}
    for _ in range(args.count):
        kind = rng.choices(kinds, weights)[0]
        owner = rng.choice(people)
        doc = make(kind, owner, people, rng)
        doc["dataset_doc_uuid"] = f"dsid_{uuid.UUID(int=rng.getrandbits(128)).hex}"
        folder = os.path.join(SOURCES_DIR, "outlook", owner["local"])
        base = f"{doc['sent_at'][:10]}-{_slug(doc['subject'])}"
        path = os.path.join(folder, f"{base}.json")
        i = 2
        while os.path.exists(path):
            path = os.path.join(folder, f"{base}-{i}.json")
            i += 1
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
        counts[kind] = counts.get(kind, 0) + 1
    print(json.dumps({"written": args.count, "mailboxes": len(people), "by_kind": counts}, indent=1))


if __name__ == "__main__":
    main()

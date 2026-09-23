Directory:
sources/sharepoint/meeting-notes

Target number of files:
1500

File name format:
YYYY-MM-DD_<meeting-name>.json in the team folder (engineering, operations, sales, exec, project-reviews).

Content rules:
Minutes of recurring meetings: weekly engineering review, daily operations huddle summaries, weekly sales pipeline review, monthly exec staff meeting, and per-job or per-initiative project reviews. Attendees, agenda, discussion in prose, decisions, action items with owners and due dates. They discuss late suppliers, ECOs, spec changes, ERP cutover problems, Queretaro ramp status, freight claims and specific jobs, POs and customers by name. 300-1200 words.

Metadata rules:
Same fields as sharepoint; document_type is "meeting_notes"; attendees is a non-empty list of real employee names.

Dates: every document carries a date field in ISO 8601 (YYYY-MM-DD, or YYYY-MM-DDTHH:MM for messages) inside the window 2025-04-01 to 2026-09-30, spread across the whole window and consistent with the initiatives roadmap (ERP go-live 2026-01-04: documents before it use legacy vendor/customer numbers, documents after it use the new numbers and sometimes both).
JSON: flat JSON only, every value a string or a list of strings, no nested objects. Field names exactly as listed below.
Entity naming: the company is Brightwater Packaging Systems, Inc. (Brightwater, BPS). Customers, suppliers, external people, part numbers, POs, sales orders, quotes and RFQs recur across the whole corpus; refer to them the way this source would (see the alias convention) and keep the same underlying entity consistent across documents (same domain, same vendor #, same PO number family).

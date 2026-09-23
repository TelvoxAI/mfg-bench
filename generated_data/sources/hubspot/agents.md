Directory:
sources/hubspot

Target number of files:
3000 (1,238 company, contact and deal records come from the CRM export via build_hubspot_records; the remaining ~1,760 documents are logged notes and call summaries and must ALL be written under hubspot/notes — never create company, contact or deal records)

File name format:
One CRM record per file: companies/<record-name-slug>.json, contacts/<first-last>.json, deals/<deal-name-slug>.json, notes/<date>-<company-slug>-<short-topic>.json.

Content rules:
CRM records for customers and prospects (not suppliers): company records with industry, plant locations and owner; contact records for plant engineers, maintenance managers and purchasing people at those companies (some of whom have changed employers during the window: a contact may exist at two companies with different dates); deals for machine opportunities and retrofit programs (stage, amount, expected close date, associated company and contacts) that later become quotes and sales orders; and logged notes and call summaries written by Brightwater sales people (150-400 words, informal). HubSpot data is maintained by Sales and is sometimes stale: old company names, contacts who have left, deals not updated after the PO arrived.

Alias convention (HubSpot): the CRM record name, usually a short trade name without legal suffix ("Precision Machining"), sometimes an old name or a misspelling that nobody fixed; contacts by full name; deals named "<customer> - <machine type> - <plant city>".

Metadata rules:
Fields common to all: object_type (company | contact | deal | note), record_id (an integer-like string), created_at (ISO 8601), last_modified (ISO 8601), owner (a real Sales employee). companies add: name, domain, industry, plant_locations (list), lifecycle_stage, description. contacts add: first_name, last_name, email, phone, job_title, company_name, previous_company (empty if none), notes. deals add: deal_name, stage, amount, close_date, company_name, contacts (list of names), machine_type, description. notes add: company_name, contact_name, note_body, logged_by.

Dates: every document carries a date field in ISO 8601 (YYYY-MM-DD, or YYYY-MM-DDTHH:MM for messages) inside the window 2025-04-01 to 2026-09-30, spread across the whole window and consistent with the initiatives roadmap (ERP go-live 2026-01-04: documents before it use legacy vendor/customer numbers, documents after it use the new numbers and sometimes both).
JSON: flat JSON only, every value a string or a list of strings, no nested objects. Field names exactly as listed below.
Entity naming: the company is Brightwater Packaging Systems, Inc. (Brightwater, BPS). Customers, suppliers, external people, part numbers, POs, sales orders, quotes and RFQs recur across the whole corpus; refer to them the way this source would (see the alias convention) and keep the same underlying entity consistent across documents (same domain, same vendor #, same PO number family).

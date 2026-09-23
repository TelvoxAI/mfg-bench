Directory:
sources/sharepoint

Target number of files:
6000

File name format:
Formal document names with a document number or date, e.g. Q-26-0412_Rev2_Case-Packer_Retrofit_Fresno.json, ECO-2026-031.json, Supplier-Scorecard-2026-Q1_V10482.json, 2026-03-12_Ops-Review.json, placed in the folder that matches the document type (quotes, customer-specs, machine-specs, ecos, supplier-scorecards, meeting-notes/<team>, procedures, service-reports, fat-reports).

Content rules:
Formal internal documents: quotes and quote revisions (scope, price, lead time, assumptions, exclusions), customer specification sheets and revisions, machine specifications, engineering change orders (reason, affected parts and jobs, disposition of parts on order, effectivity date), quarterly supplier scorecards (on-time delivery %, quality PPM, NCR count, rating), meeting notes with attendees, decisions and action items, work instructions and procedures, field service reports, factory acceptance test reports. Written in full sentences and tables rendered as text, 300-1500 words. Documents reference the same customers, suppliers, part numbers, POs, sales orders and quotes that appear in the other sources.

Alias convention (SharePoint): formal legal names, sometimes the OLD name of a company that has since been renamed or acquired, and legal names with location in parentheses ("Precision Machining, Inc. (Dayton)"). Part numbers with revision, PO and SO numbers in full.

Metadata rules:
Fields: title, document_type, document_number (empty string if none), author (a real employee), created_at (ISO 8601 date), last_modified (ISO 8601 date, on or after created_at), site (the folder path under sharepoint), body (the document text), attendees (list of names, meeting notes only, else empty list).

Dates: every document carries a date field in ISO 8601 (YYYY-MM-DD, or YYYY-MM-DDTHH:MM for messages) inside the window 2025-04-01 to 2026-09-30, spread across the whole window and consistent with the initiatives roadmap (ERP go-live 2026-01-04: documents before it use legacy vendor/customer numbers, documents after it use the new numbers and sometimes both).
JSON: flat JSON only, every value a string or a list of strings, no nested objects. Field names exactly as listed below.
Entity naming: the company is Brightwater Packaging Systems, Inc. (Brightwater, BPS). Customers, suppliers, external people, part numbers, POs, sales orders, quotes and RFQs recur across the whole corpus; refer to them the way this source would (see the alias convention) and keep the same underlying entity consistent across documents (same domain, same vendor #, same PO number family).

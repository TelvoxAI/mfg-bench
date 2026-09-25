Directory:
sources/quality

Target number of files:
150

File name format:
ncrs/NCR-2026-0142.json and supplier_corrective_actions/SCAR-2026-031.json, numbered by year and sequence.

Content rules:
Nonconformance reports raised at receiving, in assembly, at FAT or in the field: the part and revision, quantity, the supplier or internal cause, description of the defect, containment, disposition (use-as-is, rework, return to vendor, scrap), the affected machine job or PO, cost impact, and who signed. Supplier corrective action requests issued to machining and sheet-metal suppliers from NCRs: problem statement, the NCRs it covers, containment, root cause (5-why style), corrective action, due dates, verification and closure or escalation; some suppliers are on the path to disqualification under the supplier quality program. 200-700 words each, formal, written by Quality staff.

Alias convention (Quality): supplier legal name with vendor number in the header ("Precision Machining Inc. — V10482", after go-live also the new number), part numbers with revision, PO numbers in full.

Metadata rules:
Fields: record_type (ncr | scar), record_id, opened_date (ISO 8601), closed_date (ISO 8601 or empty), status, supplier_name, supplier_id, part_number, part_revision, po_number (empty if none), machine_job (empty if none), raised_by (a real Quality or Manufacturing employee), owner (a real Quality employee), severity (minor | major | critical), body (the report text), related_records (list of NCR/SCAR/PO numbers).

Dates: every document carries a date field in ISO 8601 (YYYY-MM-DD, or YYYY-MM-DDTHH:MM for messages) inside the window 2025-04-01 to 2026-09-30, spread across the whole window and consistent with the initiatives roadmap (ERP go-live 2026-01-04: documents before it use legacy vendor/customer numbers, documents after it use the new numbers and sometimes both).
JSON: flat JSON only, every value a string or a list of strings, no nested objects. Field names exactly as listed below.
Entity naming: the company is Brightwater Packaging Systems, Inc. (Brightwater, BPS). Customers, suppliers, external people, part numbers, POs, sales orders, quotes and RFQs recur across the whole corpus; refer to them the way this source would (see the alias convention) and keep the same underlying entity consistent across documents (same domain, same vendor #, same PO number family).

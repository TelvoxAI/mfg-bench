Directory:
sources/erp

Target number of files:
9000

File name format:
One record per file named by its key: purchase_orders/PO-44817.json, sales_orders/SO-2026-0187.json, vendors/V10482.json (legacy id) or vendors/200341.json (new ERP id, records created after go-live), customers/C-0412.json (legacy) or customers/100288.json (new), items/22-4410-C.json (item number with revision), shipments/SHP-26-01193.json, invoices/INV-2026-0919.json.

Content rules:
Structured ERP records rendered as flat JSON, machine-like, terse, no prose: the fields below plus line items as a list of strings. The ERP migration went live on 2026-01-04: records dated before it come from the legacy system and carry legacy vendor/customer numbers (V##### / C-####); records after it come from the new ERP, carry the new six-digit numbers and, for migrated master records, also a legacy_id field. Vendor and customer master records exist in BOTH forms for the same company (one legacy record, one new record) for every company that was migrated (most of them; a few inactive ones exist only in the legacy system). Purchase orders carry a promised date and a promised_date_history list (about 40% of POs have 1-4 revisions, each "YYYY-MM-DD -> YYYY-MM-DD (reason)"). Items carry a revision and, for about 30 parts, a supersedes / superseded_by chain (rev B -> rev C, supplier part number change). Shipments reference a PO or SO and a carrier; invoices reference a PO or SO.

Alias convention (ERP): legal name in capitals plus vendor/customer number, e.g. "PRECISION MACHINING INC — V10482" before go-live and "PRECISION MACHINING INC — 200341 (legacy V10482)" after.

Metadata rules:
Fields common to all records: record_type (purchase_order | sales_order | vendor | customer | item | shipment | invoice), record_id, record_date (ISO 8601), system (legacy | new_erp), status. purchase_orders add: vendor_id, vendor_name, buyer (a real Purchasing employee), order_date, promised_date, promised_date_history (list), ship_to (Dayton | Queretaro), lines (list of strings "line N: item number rev, description, qty, unit price, need date"), total. sales_orders add: customer_id, customer_name, customer_site, machine_job (job number), order_date, requested_ship_date, current_ship_date, ship_date_history (list), lines (list), total, project_manager. vendors/customers add: legal_name, legacy_id, new_id (empty if not yet migrated), address, city, state_or_country, payment_terms, primary_contact, contact_email, commodity (vendors) or industry (customers), notes. items add: item_number, revision, description, supplier_part_number, primary_vendor_id, supersedes, superseded_by, unit_cost, obsolete (yes/no). shipments add: reference (PO or SO number), carrier, ship_date, delivered_date, tracking, damage_reported (yes/no), notes. invoices add: reference, vendor_or_customer, invoice_date, due_date, amount, paid_date, dispute_notes.

Dates: every document carries a date field in ISO 8601 (YYYY-MM-DD, or YYYY-MM-DDTHH:MM for messages) inside the window 2025-04-01 to 2026-09-30, spread across the whole window and consistent with the initiatives roadmap (ERP go-live 2026-01-04: documents before it use legacy vendor/customer numbers, documents after it use the new numbers and sometimes both).
JSON: flat JSON only, every value a string or a list of strings, no nested objects. Field names exactly as listed below.
Entity naming: the company is Brightwater Packaging Systems, Inc. (Brightwater, BPS). Customers, suppliers, external people, part numbers, POs, sales orders, quotes and RFQs recur across the whole corpus; refer to them the way this source would (see the alias convention) and keep the same underlying entity consistent across documents (same domain, same vendor #, same PO number family).

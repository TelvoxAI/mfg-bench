Directory:
sources/outlook/shared

Target number of files:
1500

File name format:
Same as outlook: date + subject slug, one email per file, in the folder of the shared mailbox it landed in (sales, service, parts, rfq, accounts-payable).

Content rules:
Inbound mail to the shared mailboxes: new RFQs from prospects and customers (rfq@), parts orders and part-number questions (parts@), service call requests and machine-down reports (service@), supplier invoices and payment status questions (accounts-payable@), general sales inquiries (sales@). Often the first message of a thread that a named employee later continues from their own mailbox. Follows every rule of the outlook agents.md, including the alias convention and the date window.

Metadata rules:
Same fields as outlook; mailbox is the shared mailbox name.

Dates: every document carries a date field in ISO 8601 (YYYY-MM-DD, or YYYY-MM-DDTHH:MM for messages) inside the window 2025-04-01 to 2026-09-30, spread across the whole window and consistent with the initiatives roadmap (ERP go-live 2026-01-04: documents before it use legacy vendor/customer numbers, documents after it use the new numbers and sometimes both).
JSON: flat JSON only, every value a string or a list of strings, no nested objects. Field names exactly as listed below.
Entity naming: the company is Brightwater Packaging Systems, Inc. (Brightwater, BPS). Customers, suppliers, external people, part numbers, POs, sales orders, quotes and RFQs recur across the whole corpus; refer to them the way this source would (see the alias convention) and keep the same underlying entity consistent across documents (same domain, same vendor #, same PO number family).

Directory:
sources/outlook

Target number of files:
27000

File name format:
One email per file, named by date and a short slug of the subject, e.g. 2026-03-04-po-44817-promised-date-slip.json. Files live in the mailbox folder of the Brightwater employee who owns that mailbox (the folder name is the employee's email local part, e.g. outlook/laura.kim/); shared/ holds the shared mailboxes (sales@, service@, parts@, rfq@, ap@brightwaterpkg.com).

Content rules:
Business email as it really looks: RFQs and quotes, PO confirmations and promised-date changes, expedite requests, ECO notifications, customer spec changes after PO, freight damage and claim disputes, shipment notices, invoice questions, service scheduling, parts orders, internal forwards with a one-line comment on top of a quoted thread. About 60% of emails involve an external party (customer, supplier, carrier); 40% are internal. Many emails are replies and carry the earlier messages quoted below a separator line, so one file can hold a whole thread. Bodies are 80-600 words, written by people, with greetings, signatures (name, title, company, phone) and occasional typos. Suppliers and customers write from their own company domains; about 20 small suppliers (job shops, a freight broker, a used-equipment dealer) write from gmail.com addresses with the company name only in the signature.

Alias convention (Outlook): informal and inconsistent. People call companies by short names, abbreviations and nicknames ("the guys at PMI", "Precision", "@precisionmach.com"), refer to people by first name, quote PO and part numbers loosely ("PO 44817", "po#44817", "the 22-4410 rev C bracket"), and after the ERP go-live sometimes mention both the legacy vendor number and the new one ("V10482, now 200341 in the new system").

Metadata rules:
Fields: subject, from (one email address, display name optional as "Name <address>"), to (list of addresses), cc (list, may be empty), sent_at (ISO 8601 with time), mailbox (the owner folder), thread_subject (the subject without Re:/Fwd:), body (the full email including any quoted messages), attachments (list of file names, often empty). Every from/to address of a Brightwater employee must be a real person from the employee directory; external addresses use invented company domains that stay stable for that company across the corpus.

Dates: every document carries a date field in ISO 8601 (YYYY-MM-DD, or YYYY-MM-DDTHH:MM for messages) inside the window 2025-04-01 to 2026-09-30, spread across the whole window and consistent with the initiatives roadmap (ERP go-live 2026-01-04: documents before it use legacy vendor/customer numbers, documents after it use the new numbers and sometimes both).
JSON: flat JSON only, every value a string or a list of strings, no nested objects. Field names exactly as listed below.
Entity naming: the company is Brightwater Packaging Systems, Inc. (Brightwater, BPS). Customers, suppliers, external people, part numbers, POs, sales orders, quotes and RFQs recur across the whole corpus; refer to them the way this source would (see the alias convention) and keep the same underlying entity consistent across documents (same domain, same vendor #, same PO number family).

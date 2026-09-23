Directory:
sources/teams

Target number of files:
13200

File name format:
One conversation thread per file, named by date and a short slug of the topic, e.g. 2026-02-11-drives-backorder-job-4471.json, inside the channel folder. Channels are one level deep (no nested directories): function channels (sales, purchasing, quality, manufacturing-dayton, manufacturing-queretaro, field-service, ...), project channels (proj-erp-migration, proj-dual-source-drives, proj-queretaro-ramp, proj-aftermarket-push, proj-beverage-retrofit, proj-supplier-quality), job-escalations for machine jobs in trouble, and social channels (random, dayton-social, queretaro-social).

Content rules:
Short, fast, internal chat between Brightwater employees only: status pings, "where is the PO", "customer just changed the spec", ECO heads-up, supplier late again, freight claim updates, shift handoffs, who-has-the-drawing, quick decisions, links to SharePoint documents by title. Threads are 3-25 messages, each message 5-60 words, with slang, abbreviations, typos and emoji-free plain text. Manufacturing-queretaro and queretaro-social are mostly in English with occasional Spanish words and Spanish names. Social channels are noise: lunch, sports, parking, weather.

Alias convention (Teams): nicknames, abbreviations and typos. Companies by initials or a mangled short form ("PMI", "Precison", "the Dayton machine shop"), people by first name or initials, part numbers without the revision, POs as "44817" alone, customers by plant city ("the Fresno plant") as often as by name.

Metadata rules:
Fields: channel, started_at (ISO 8601 with time of the first message), participants (list of employee names), topic (one line), messages (list of strings, each "YYYY-MM-DD HH:MM Author Name: message text", in order). Every author must be a real employee from the directory.

Dates: every document carries a date field in ISO 8601 (YYYY-MM-DD, or YYYY-MM-DDTHH:MM for messages) inside the window 2025-04-01 to 2026-09-30, spread across the whole window and consistent with the initiatives roadmap (ERP go-live 2026-01-04: documents before it use legacy vendor/customer numbers, documents after it use the new numbers and sometimes both).
JSON: flat JSON only, every value a string or a list of strings, no nested objects. Field names exactly as listed below.
Entity naming: the company is Brightwater Packaging Systems, Inc. (Brightwater, BPS). Customers, suppliers, external people, part numbers, POs, sales orders, quotes and RFQs recur across the whole corpus; refer to them the way this source would (see the alias convention) and keep the same underlying entity consistent across documents (same domain, same vendor #, same PO number family).

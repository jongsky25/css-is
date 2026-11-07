# Find a file or email in the Inbox — 10.11

The Inbox search matches original file names and email subjects across the whole
permitted queue. Search combines with status and review availability before
pagination; status and availability counts use the same search. Email attachment
siblings still count as one primary entry. Inaccessible linked records remain
excluded from results and counts.

Submitting a search starts at page one and retains the selected status and review
availability. Pagination, status/availability links and return-to-Inbox links keep
the search. Clear search retains the current status and availability. The native
GET form works on phones and without JavaScript; typing or searching never claims
work or invokes an external service.

Search is a literal substring, using SQLite's built-in lowercase comparison
(ASCII case folding). Percent signs and underscores are literal characters, not
wildcards. The server trims and bounds the query to 120 characters; parameters
are bound and rendered values/links are escaped. Email bodies, attachment contents,
OCR drafts and secondary attachment names are outside this search. Those contents
are not loaded into queue results. Existing claim/revision/CSRF and review checks
remain in force after navigation.

Verification: 75 existing intake, availability, email and navigation checks plus
six new service/route/browser checks passed without failures or skips. New cases
cover filtering beyond page one, matching counts, active claims, literal wildcard
characters, email subjects counted once, restricted/secondary exclusions, escaped
and bounded input, phone layout, no-script operation, and search retention after
claiming and returning. Version 10.11 metadata and whitespace checks passed.
Full current-head normal/shuffled CI remains required before merge.

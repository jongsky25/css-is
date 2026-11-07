# Progressive document request entry

Candidate 10.07, November 7, 2026. Branch `feat/documents-request-entry`,
initially based on intake PR #597. This increment is for draft review only.

Request forms now start with existing entries and an **Add request** button.
Completely empty slots remain in the form with unchanged field names and default
values but are hidden when JavaScript is available. Adding a request reveals one
slot, expands it and focuses its requested-action field. At five visible forms,
the button disables. Request slots are never renumbered, deleted or cloned.

Any entered text, selected nondefault interpretation or checked confirmation
keeps its slot visible. Validation responses therefore show partial requests,
even when their action is missing. Clearing a form during editing does not hide
it unexpectedly. Accepted source suggestions reveal an empty slot and preserve
partial entries. Source changes and edits still invalidate confirmations through
the existing handlers. Showing a form does not assign work or change saved data.

Without JavaScript all five native request disclosures remain available, exactly
as before. The Add request control stays hidden. Server validation, source
comparison, review history, permissions, numbering and proposal identity are
unchanged; no schema, dependency or provider change.

Verification covers keyboard focus, empty/add/max states, retained form payload,
partial suggestions, source-change confirmation clearing, error rerenders with
stable slot numbers, escaping, saved requests, and saving a new request with and
without JavaScript at phone width. The combined browser/registration/review/
understanding/request-work regression run passed 102 checks without skips. All five final
focused browser checks passed, including saved-request persistence in both script modes.
Full normal/shuffled CI remains required; synthetic local checks do not establish
staff timing improvements or live Google preview behavior.

The owner authorized merging #596 and #597 when ready, in order with guarded
predecessor deployment success. This next increment is implemented for review;
there is no authorization to merge/deploy 10.07 yet.

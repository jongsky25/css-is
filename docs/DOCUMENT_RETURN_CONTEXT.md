# Return to your place in Documents — 10.08

Opening a record from the register, My desk or Inbox now carries a return link.
It keeps the queue/search and page parameters and points back to the originating
row when that row is still present. The interactive register captures the actual
successful table request, including applied filters, sort and page; returning
reopens that view. Native register and Inbox links also work without JavaScript.

The same return link follows document subpages, source-file selection and normal
form saves. Actions still use their existing POST, CSRF, revision, claim and
permission checks. Reads do not mutate documents or call external providers.

`documents_navigation.py` accepts only the three known local queue paths and
allowlisted query keys, bounds context length and field count, rejects control
characters and external URLs, and permits only generated row fragments. Context
is navigation only: all destination routes recheck current access. No browser
storage, schema, dependencies, integration configuration or production data use.
The new helper is included in the explicit deployment runtime manifest.

Position restoration is best effort: a completed item may disappear from its
queue, and data or permission changes can change the page. This does not retain
pixel scroll position, unsaved form edits, transient column widths/visibility or
return context across other modules. Personal saved views remain available for
column preferences. Queue counts and further filtering improvements are separate.

Verification includes URL validation, escaped/normalized context, filtered queue
links, successful save redirects and revoked access; real Chromium interactive
page/filter/sort restoration and native navigation with scripts disabled; existing
intake, workspace, pagination, guidance and progressive request-entry regressions;
and release metadata/deployment bundle checks. Full normal/shuffled CI is still
required on the eventual main-reconciled head before merge.

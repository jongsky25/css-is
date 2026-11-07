# Manual-first correspondence registration — 10.09

Registration now starts with Incoming / Outgoing draft and a short explanation
of each choice. Editable details are visible immediately. The optional PDF/link
reader sits in a native disclosure; opening it retains all existing controls,
source notes, cancellation and rereading behavior. Linked-source suggestions
render with the disclosure open. Reading still requires JavaScript; manual
registration works without it.

This removes the prerequisite “Skip and enter manually” click and hides the long
reader controls until requested. The original skip/clear action remains inside
the reader for people switching away from an attempted read. Merely opening or
closing the disclosure never clears values, starts reading or submits a record.

Direction moved outside the details section, so its change explicitly invalidates
approval. Existing confirmation, proposal/assignment distinctions, source-change
checks, CSRF, server validation, permanent numbering and retry-safe registration
remain. Outgoing registration creates a draft; it does not authorize release.
No backend, schema, dependency, permission or integration configuration changes.

Verification uses synthetic browser and registration fixtures, including phone
width, direct manual input, direction-change reapproval, preserved values,
source-change confirmation, no-script registration and uncertain-save retries.
Legacy PDF browser fixtures now supply the current focus-area context and open
the optional reader explicitly. Their worker expectation matches the existing
policy that registration bypasses service-worker replay. Production worker logic
is unchanged apart from the release cache version.

Remaining work: truthful scoped queue counts/ready-waiting filters and closer
request-execution/source-reconciliation flows. Staff completion times have not
been measured. Full current-head normal/shuffled CI remains required before merge.

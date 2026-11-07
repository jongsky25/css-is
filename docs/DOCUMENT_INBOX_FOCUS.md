# Inbox review availability — 10.10

Waiting and Needs attention now offer All reviews, Ready to review, My reviews,
and With other reviewers. Ready means no active claim, including expired claims;
it does not assert that the source is verified or otherwise safe to register.
My reviews means an active claim belonging to the current reviewer.

Filtering runs in SQL before pagination. Counts span the complete selected status
queue, use the same existing visibility predicate, and count primary email entries
once rather than each attachment. Registered and Dismissed retain their existing
views. A single request timestamp determines expiry for rows, counts and actions.
Counts are a point-in-time view; concurrent claims can change availability.

Links reset pagination when changing availability, retain availability across
pages, and carry it through the existing return-to-Inbox context. Native links
and existing Review/Resume POST forms work without JavaScript. Reading/filtering
does not acquire claims, start a provider call or mutate a document. Claim POSTs
still enforce CSRF, revision, current authority and exclusive active claims.

No schema, dependency, relay, notification or deployment-setting change. Existing
page size and lightweight queue metadata remain. This increment is limited to
Inbox review availability; My desk state filters/counts require a separate design
that classifies the complete authorized workflow scope before pagination.

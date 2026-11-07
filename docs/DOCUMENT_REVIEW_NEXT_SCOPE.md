# Review the next matching Inbox item — 10.12

Register and review next now follows the originating Inbox's status, search and
review-availability filter. Selection covers the full permitted matching queue,
not just the current page, in the same oldest-entry order. It selects only primary
entries that have not been registered and can be claimed by this reviewer. Active
claims held by other staff are skipped. An expired or null-expiry claim is treated
consistently with Inbox availability.

The next item's current revision and claim authority are checked by the existing
claim operation. If no candidate exists or another reviewer wins the claim, the
completed registration stays saved and the user returns to the same filtered
Inbox (page one). The notice states that no next review was opened; it does not
claim the entire Inbox is empty. There is no automatic retry or claim takeover.

A validated local Inbox return context supplies the filters. Absent, unrelated or
unsafe return URLs use the normal Waiting/All reviews scope. Registered/Dismissed
contexts also default to Waiting. No external redirect is permitted. Search uses
the existing bounded literal name/subject match. Reads of the selection helper do
not claim work, mutate entries or call providers. Numbering, source checks, human
confirmation, CSRF, authority and registration itself remain unchanged.

Phone and desktop journeys still register and open an unfiltered next item. New
phone cases with JavaScript on/off confirm that a completed filtered batch returns
to its original search rather than opening an unrelated file. Service/route cases
cover selection beyond page one, other staff claims, own/ready scopes, null expiry,
attention scope, no matches, invalid return URLs and a concurrent claim after
successful registration. No production data or external notifications are used.
Full current-main CI and predecessor deployment success remain merge prerequisites.

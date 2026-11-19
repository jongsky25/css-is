# Division follow-up counts and filters — candidate 10.39

Division follow-up previously paginated exceptions before displaying guidance and
had no full-scope state counts or state/overdue filters. It now counts the complete
currently permitted exception queue and filters before choosing the page.

The existing chief/OIC division scope, document visibility, exception eligibility
and deadline/ID sort are unchanged. This is not a count of every document in a
division: closed, archived, canonicalized and non-exception documents remain out.
Ready for you means the viewing chief/OIC has an available document action.

Counts represent documents with a matching guidance state, using the same
classifier and overdue predicate as My next steps. Division follow-up has one
workflow card per document; it does not add personal instruction/contribution
cards. My next steps can therefore have overlapping groups while division's
workflow groups are disjoint. Unknown document deadlines are not overdue, even
when a contribution deadline caused the document to enter the exception queue.

The existing bounded-memory streaming fallback is shared between the views.
Division does not use the personal cache or expand its cache keys. Classification
reads batches of 1024 inside one SQLite snapshot, keeps only a page plus one
matching document, and counts the entire permitted scope. Consequently each
Division page is proportional to eligible scope. Synthetic 1000-document local
measurement was 0.030 seconds; this is not a production latency promise. The
previously accepted 10k performance exception is unchanged.

Native GET controls work without JavaScript. Filter application resets the
cursor; pagination and document return links retain view/state/overdue. Counts
and page data share current permissions and a snapshot, and responses remain
private/no-store. No database migration, business writes or external notifications.

Verification covers independent truth sets over multiple pages/batches, restricted
and out-of-division exclusion, current OIC revocation, unknown deadlines, disabled
modules, private shared-work guidance, synthetic scope measurement, and phone
keyboard filtering/page/document/return journeys with JavaScript on and off.
Full hosted release CI remains mandatory. This increment is a draft review only;
merge and production deployment are not authorized.

Final local acceptance: 49 tests passed with no failures/errors/skips, including
all existing action-page/route and personal-filter regressions. JUnit gate,
10.39 release metadata and diff checks passed. Hosted full CI remains pending.

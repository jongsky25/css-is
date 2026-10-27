# Correct the application proof API to match its qualified witness

Attempt2 (5146cad/dd0f4e1, run40518161854) passes full native qualification in its
actual allocated job. One complete unchanged app proof workload also completes:
13 snapshots, 20 navigations. The proof captures128 native namespace-getter calls
but zero reference calls; the required phase-identity checker fails and no app
calibration slot starts. All raw data and the complete native pass are retained.

Concrete harness bug: the new application reference query calls getBoundingClientRect,
while the retained qualified native offset0x100b1880 is Element::getClientRects.
Both qualified mixed_getter_capability.py and absent_attribute_capability.py call
getClientRects. Symbol resolution also names getClientRects (line decoding reports
DWARF warnings, so no source-line claim). No method substitution can establish the
required native identity proof; the gate correctly rejected it.

Repair only the reference query to call getClientRects and retain its actual list
length. Allow nonnegative counts, including zero for hidden defs/stops/scripts;
rectangle dimensions/visibility are not the identity criterion. Require32 actual
integer count witnesses per reference query, plus unchanged128 native reference/
128 getter identity/null/source/attribute gates. No getter, agent, selector, sample,
app workload, measurement cost, stability or reclamation threshold is changed.
Geometry remains proof-only. No unproved listener/JIT/lifetime explanation is used.

Freeze source/tests before the distinct corrected attempt. Keep same-job native
qualification and all app prerequisite gates; stop before four slots on any proof
failure. Close the superseded setup PR516 and open an opened-only corrected setup
PR. Never re-run an unchanged failed job or replace any earlier observation.

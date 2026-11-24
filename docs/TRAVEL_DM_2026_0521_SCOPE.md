# Travel filing vs DM 2026-0521 — improvement scope

Source: DOH Department Memorandum No. 2026-0521 (October 29, 2026), "Streamlined Processing of
Travelling Expenses based on 2026 Pre-Audit Observations". It cites PD 1445, EO 77 s. 2019,
DO 2019-0225, DM 2023-0092 and DM 2024-0369. The memo itself is not committed; this file
records only its directives and how they map onto Travel filing.

Status: scoped November 24, 2026; owner decisions recorded below; **DM1 and DM3 built** (candidate 10.47) on `claude/cool-davinci-y5s3re`, PR #640.

DM3 as built: per diem days start with meals and lodging ticked as provided (server defaults, upload drafts and the
prepare page; a browser draft saved before 10.47 is reset to provided, with a notice). The generate step stores the
derived answer `meals_not_provided`; the checklist row `meals_lodging_cert` is now a generated "Certificate of
Non-Provision of Meals and Accommodation", required for a liquidation or reimbursement with per diem until the itinerary
shows every day provided. It lists one line per unticked day (meals, lodging, or both) and is signed by the approver
(head of office by default). Its Google template is written by `makeNonProvisionTemplate()` in
`apps_script/travel_templates.gs` and must be run once by a person; until then the person pastes their own copy.
Certificate wording needs the owner's approval.

## 1. Directive-by-directive gap map

| # | Memo directive | What Travel filing does today | Gap |
|---|---|---|---|
| A | **Per diem**: no full DTE/DSA when the host or region provided meals or lodging. The signer of the Certificate of Non-Provision of Meals and Accommodation is accountable; a wrong certificate is not honoured. | Prepare page has per-day "Meals were provided" / "Lodging was provided" ticks (`static/js/travel_prepare.js:297`), and `travel_rates.day_amount` removes those shares. Checklist row `meals_lodging_cert` is an upload with "Template pending" (`travel_checklist.py`). | Ticks default to **not provided** and nothing cross-checks them. No generated certificate; signer is not warned about accountability. The platform already knows things that contradict a "not provided" claim: room reservations with `meals_requested` linked to the activity (`room_reservation.event_id`/`calendar_entry_id`), meal requests, the activity's "Meals" document item (`activity_docs.py`), and registration's accommodation question (`reg_questions.py`). |
| B | **TNVS**: FMS will validate digital receipts on the claimant's app/email; dates, reference numbers, duration, distance and rates must match the approved Itinerary of Travel. Unverified or inconsistent receipts are not paid. | Receipt reading (`travel_scan.py`) keeps kind, amount, date, origin, destination, vendor, reference, depart/arrive times. Rides are checked against ceilings (`travel_rules.ride_check`). | No comparison of the receipt reading with the itinerary row it supports (date, from/to, time, amount). No reminder that the original must stay in the app/email for FMS to inspect. Distance/duration not read. |
| C | **Multi-stop / multi-passenger TNVS** only if: all co-passengers' DVs go together, consistent with IT, fare split per destination shown, and justified as more advantageous. Otherwise not honoured. Single-passenger point-to-point is ideal. | Nothing reads stops or passengers. `travel.peers_of` already finds the co-travellers on the same activity and DPO. | No question, reading or flag for multi-stop/shared rides; no check that co-passengers' filings are ready together; no justification item. |
| D | **Airfare**: screenshots of fare options taken immediately before booking, showing timestamp, date and fares — proof of lowest regular economy (DM 2024-0369). Allowed brands named (Cebu Pacific GO BASIC / GO EASY; PAL Economy Supersaver / Saver / Value / Flex). PAL round trip needs outbound **and** return screenshots unless both are Supersaver. | `plane_fare_proof` upload required for CA/reimbursement when flown; for a liquidation only when "fare differs from lowest economy". Ticket reading has no fare brand/cabin. | No fare-brand capture or allow-list; no check that the screenshot predates the booking; no second-screenshot rule for PAL round trips; checklist note only says "Lowest economy fare". |
| E | **Premium economy / comfort / business** prohibited unless approved in advance by the Office of the President. | Not checked. | Needs a flag when the ticket reading shows a non-allowed cabin/brand. |
| F | **Baggage**: extra baggage on the return leg is not allowed by default when the outbound had none; must be for official use with justification; personal baggage refused. | One answer, `extra_expenses` ("baggage, rebooking, cancellation"), drives invoice + justification uploads. | Baggage is not separated per leg, so the outbound/return rule cannot be checked; justification template is still "pending". |
| G | **Cash advance lead time**: request to FMS at least 3 working days before departure, complete and approved; late or materially incomplete requests not received. Urgent/unplanned travel may use an expedited window with an approved travel authority and written justification. | Owner rule: CA only when the activity starts more than 7 days away (`travel_rules.ca_lead_error`); otherwise forced to reimbursement. A CA filing has **no deadline** (`deadline_for` returns none), so no reminder before departure. | No "hand in by" date (start minus 3 working days) or reminder for CAs. No expedited path for urgent travel (currently impossible to file a CA inside 8 days at all). |
| H | **No new CA while one is unliquidated**; "liquidated" means the Liquidation Report is **certified by the accountant**. Failure means automatic denial. | `create_filing` only warns (`Unliquidated`, overridable with `acknowledged`). `unliquidated_cas` treats any non-withdrawn liquidation filing — even one still in progress — as liquidating it, and only counts CAs whose activity has ended. | Warning should become a block (or at least not be overridable). Platform has no "LR certified" state; "liquidated" is inferred from an open filing. |
| I | **Liquidation deadline**: 7 days after return for local travel, 30 calendar days for foreign travel; late → Notice to Liquidate and lower FMS queue priority. | Liquidation/reimbursement due 5 working days after the last day (`DUE_WORKING_DAYS`), daily reminder job `travel_filing_due`. Foreign travel not modelled. | 5 working days can exceed 7 calendar days around holidays. No foreign-travel rule. Reminder text does not mention the Notice to Liquidate consequence. |
| J | Offices must **review all DVs and supporting documents** before submitting to FMS. | Admin Unit verify queue handles flags only; optional reviewer request exists (`travel_review.py`). | No office pre-audit pass over a whole ready filing against the memo's points. |
| K | **Falsified/tampered receipts**: written explanation, reported to Head of Office and Administrative Service for discipline. | No statement shown. | Add an attestation and warning at "Mark ready". |

## 2. Proposed increments (each one PR, smallest first)

**DM1 — Rules text, deadlines, attestation (no schema change).**
- Guidance and checklist notes: TNVS originals kept for FMS validation; single-passenger point-to-point preferred; screenshot-before-booking and allowed fare brands; PAL round-trip second screenshot; baggage rule; personal-baggage refusal.
- Liquidation/reimbursement deadline = the **earlier** of 7 calendar days and 5 working days after the last day (`travel_rules.deadline_for`); reminder mentions the Notice to Liquidate.
- CA "hand in to FMS by" date = 3 working days before the start, shown on the filing and in the `travel_filing_due` reminder.
- "Mark ready" attestation: receipts are genuine and unaltered; certificates are accurate (falsification consequences stated).
- Signer warning on the meals/lodging certificate row (accountability, not honoured if wrong).

**DM2 — Cash-advance guardrails.**
- Block a new CA while any earlier submitted CA has no **submitted** liquidation (today an in-progress one is enough, and the warning can be acknowledged away).
- Optional "LR certified on" date on the liquidation, recorded by the person or the Admin Unit; only then is the CA counted as liquidated.
- Urgent-travel CA path inside the owner's 7-day window: requires an approved DPO/travel authority and a written justification upload; Admin Unit verifies.

**DM3 — Certificate of Non-Provision, with cross-checks.**
- Generate the meals/lodging certificate from the per-day ticks (replaces the "template pending" upload).
- Pre-tick "provided" when platform data shows it (room reservation with meals for the activity, meal request, activity's Meals item, registration accommodation, invitation text); unticking needs a short reason, which goes to the Admin Unit as a flag.

**DM4 — Smarter receipt and ticket readings.**
- Extend the receipt reading with: stops, passengers, fare split shown, distance, duration, receipt source (app/email export vs screenshot); and the ticket reading with fare brand/cabin and booking time; and a new fare-screenshot reading with its timestamp.
- New checks: receipt ↔ itinerary row mismatch (date, route, time, amount); multi-stop/multi-passenger without justification or with co-passengers' filings not ready together (`peers_of`); non-allowed cabin/brand; screenshot later than booking; PAL round trip with one screenshot.
- Needs a `travel_flag.kind` migration: the table's CHECK allows only four kinds (`storage.py:839`); per diem already piggybacks on `over_ceiling`. A table rebuild adding e.g. `receipt_mismatch`, `shared_ride`, `fare_class`, `fare_proof` is cleaner than more piggybacking.

**DM5 — Baggage per leg.** Split "extra expenses" into outbound baggage, return baggage and other; flag return-only baggage; generated justification asks what official items were carried.

**DM6 — Office pre-audit (optional).** A "pre-audit" view for the Admin Unit over ready filings, listing each memo point as checked/unchecked before papers go to FMS.

**Later / decision first — Foreign travel** (30-day liquidation, different rates). Not modelled today.

## 3. Owner decisions (November 24, 2026)

1. **Deadline**: earlier of 5 working days and 7 calendar days after the last day. Built in DM1.
2. **Unliquidated CA**: accountant certification is external (FMS). No hard block and no "LR certified" tracking;
   the warning stays acknowledgeable, with stronger wording. DM2 is reduced to the urgent-travel path.
3. **CA timing**: keep the owner's 7-day rule and add the memo's urgent/expedited path (DM2).
4. **Meals/lodging**: every day defaults to **provided**; the person unticks a day to claim it, and the
   unticked days drive the Certificate of Non-Provision (DM3). No cross-checking of other platform data needed.
5. **AI reading** for TNVS receipts, tickets and fare screenshots: yes (DM4).
6. **FMS checklist**: still `FMS-BD-01 r6 2025-06`; adopt this memo's changes on top of it for now.
7. **Foreign travel**: out of scope.

### Originally asked

1. Liquidation deadline: earlier of 7 calendar days / 5 working days (proposed), or switch to the memo's 7 days only?
2. Unliquidated CA: hard block (memo reading) — and does "liquidated" need an accountant-certified LR date, or is a submitted liquidation enough for the platform?
3. Keep the owner's 7-day CA rule, and add the memo's urgent/expedited path inside it?
4. Cross-check sources for meals/lodging (DM3): which are reliable enough to pre-tick "provided"?
5. Is DM4's AI reading of TNVS/fare screenshots wanted (more uploads read by the model), or checklist text and manual Admin Unit checks only?
6. Is the FMS checklist still `FMS-BD-01 r6 2025-06` (`travel_checklist.CHECKLIST_REV`), or did FMS issue a revision with this memo?
7. Is foreign travel in scope?

Recommended start: **DM1** (low risk, no schema change, covers the deadline and attestation points), then DM2.

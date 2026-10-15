# Travel policy rates — plan v1 (T9)

Source: DOH Department Order No. 2019-0225 (July 10, 2019) and its amendment No. 2019-0225-A (November 22, 2019), with Annex A (COA Circular 2017-001), Annex B (LTFRB fare guide) and Annex C (airport taxi rates by area). This closes the open item "Per diem and transport allowance rules: manual entry until supplied" in `docs/TRAVEL_FILING_PLAN.md`.

## 1. What is automated
The prepare page (`/travel/f/{ref}/prepare`) used to take every amount by hand. Now the person chooses where they went and how each day and ride was spent, and the page shows the most the policy allows, with the rule and section behind it and a button that copies the amount in. The person still types what was actually spent; anything above the limit is flagged for the Admin Unit exactly as an over-ceiling fare was before.

| Rate | Where it comes from | Where it applies |
|---|---|---|
| DTE by cluster: 1,500 / 1,800 / 2,200 for the 17 regions | VI.A.2.h(1) | "Where you are going" |
| Full day 100% (lodging 50, meals 30, incidentals 20); departure day 50% (meals 30, incidentals 20) | VI.A.2.i(1) | Per diem rule: Full day, Departure day |
| Php 50 subsistence allowance off the meals of a working day | VI.A.2.i(2) | "I receive the subsistence allowance" |
| Live-in: nothing in between, incidentals 20% the day before and after | VI.A.2.i(3) | Per diem rule: Live-in, Day before or after |
| Lodging or meals provided: that part not allowed | VI.A.2.k | "Lodging / Meals were provided" |
| Within 50 km, going home each day: meal allowance 20% (+10% past 7 PM), liaison 10%, HPDPB-LLD 20%, incidentals 20% for a meeting past 7 PM | VI.A.3.b(2)-(4) as amended | Per diem rule: the "Within 50 km" group |
| Taxi to an official activity: 550. TNVS: 700 | VI.A.2.b(1) | Fare rate: Taxi or TNVS to an official activity |
| Airport taxi by area, 57 areas from 150 to 550; outside Metro Manila 550 | Annex C, VI.A.2.f as amended | Fare rate: Residence or station ⇄ airport |
| Seaport or bus station taxi by area: 350 / 400 / 500 / 550 | VI.A.2.f (original table) | Fare rate: seaport or bus station |
| DOH shuttle catch, 3 days or more: 100 / 250 / 300 / 400 / 450 | VI.A.2.g | Fare rate: ... to catch the shuttle |
| Live-out within 50 km by distance: 100 / 250 / 300 / 400 / 450; without an official receipt only 300 | VI.A.3.c as amended; COA 2017-001 | Fare rate: Taxi for a live-out activity |
| LTFRB bus fare by km, regular and senior / PWD / student | Annex B, VI.A.2.a | Fare rate: Public fare beyond 50 km |

Every rate is printed, with its section, on the Policy rates tab (`/travel/rates`).

## 2. How it is built
- `travel_rates.py`: pure tables and functions (`day_amount`, `row_cap`, `rates_for_rows`, `ltfrb_fare`, `live_out_max`, `find_areas`). No database, no request. The working-day lookup is passed in, so the module stays pure.
- `travel_rules.ride_check` takes an optional `cap`. With one, that is the limit for the ride on any document (a receipted fare and a CENRR-sized fare are both held to it) and the route counts as approved, because the policy names it. Without one, behaviour is exactly as before. `flags_for` also flags a day whose per diem is above what its rule allows.
- A per-diem flag is stored under the existing kind `over_ceiling`: the `travel_flag` table only allows four kinds and rebuilding a CHECK constraint on a live database was not worth it. `travel_rules.flag_label(kind, detail)` heads it "Per diem above the policy rate" on the verify page.
- `POST /travel/f/{ref}/rates` is a read-only calculator: the page posts its rows and options, the server answers per row. One copy of the rules, no mirror in JavaScript. It stores nothing, so it is not audited (it sits in `NOT_AUDITED` beside `travel_link_check`) and is rate limited per account (bucket `travel_rates`). `generate` recomputes everything on the server and never trusts the page.
- Per-row fields `basis`, `place`, `km`, `day_kind`, `lodging_provided`, `meals_provided` and the claim-level `rates` (region, receives_sa, discounted) are posted with the rest of the prepare form and, like it, never stored.
- The Annex B tables are checked in `tests/test_travel_rates.py` against the add-on method printed on the annex (all 60 fares, both columns), which independently confirms the transcription.

## 3. Readings the owner should confirm
1. **Departure day** is 50% of the DTE (the policy's 50% row covers meals 30 + incidentals 20, which is 50% of the DTE).
2. **Liaison officer**: amendment A restates the rule as 10% of the DTE for leaving by 8:00 AM. The original's extra 10% for returning after 3 PM is not in the amended text, so it is not applied.
3. **Live-in**: days with hotel and meals provided pay nothing; the incidentals of 20% are for the day before and the day after (VI.A.2.i(3)).
4. **Meeting past 7 PM, within 50 km** (VI.A.3.b(3)(b)) says incidentals "based on" the DTE section; read as 20% of the DTE.
5. **Subsistence allowance** is only deducted when the person ticks the box (default off), and comes off any meals amount on a working day, including a within-50 km meal allowance.
6. **Within 50 km** uses whichever region the person picks; in Metro Manila that is NCR (Cluster III, 2,200).
7. **A part of a kilometre** counts as a whole one for the LTFRB fare and for the live-out distance bands.
8. **Taxi ceiling**: the seeded flat "Metered taxi" ceiling is 700, but VI.A.2.b(1) says 550. The policy rate (550) applies to rides that use the "Taxi or TNVS to an official activity" rate; the flat ceiling still governs a fare typed in by hand. The Administrative Section may want to lower it to 550 on Ceilings and routes.
9. **Annex C was typed from a scan**; a place in two areas (e.g. Sta. Ana) is listed under each, as printed. A few spellings were tidied (Napindan, Muntinlupa). The Admin Unit should read the Policy rates tab against the issuance once.

## 4. Not automated, on purpose
- **Foreign travel** (DSA from the UNDP ICSC tables, clothing allowance, pre-departure Php 3,500, representation expenses, insurance Php 500,000): this module files local travel only, and the DSA table is an outside document that changes.
- **Registration and course fees** (Php 2,000 a day for non-government conventions): the prepare forms have no fee field.
- **Excess lodging up to 100% more** (VI.A.2.j) needs the agency head's certification; it is a person's decision, so it goes through the Admin Unit as any over-limit amount does.
- **Other offices' fare matrices** (the Centers for Health Development issue their own), **private vehicle** (the fare of the customary mode) and **government vehicle** (no fare claim; the page only warns).
- **Rates do not change by date.** When a new order replaces these, edit `travel_rates.py` and the tests together.

## 5. Increment
T9, one PR: engine and tables, rules and flags, calculator route, prepare page, rate card page, tests.

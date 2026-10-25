# FullCalendar Schedule pilot

Open **Calendar → Schedule**, or choose Schedule on the home Calendar tab. The wide view places recorded events on a Monday–Sunday hour grid, making overlapping times easier to see. Phones show one day; **Show day** selects another day within the displayed week. The existing week links move between weeks. Scope, type, status, tag, unit and text filters still apply. **Save as preferred view** reuses the existing personal calendar cookie.

The existing **Week** view remains the people/whereabouts view. Schedule is a separate presentation of the same authorized calendar layers. It does not compute availability or decide whether overlapping events are conflicts. Use the usual Add/Edit pages for changes; the grid has no drag, resize, selection or booking writes. Event links retain the ordinary record pages and existing calendar-item sheet.

## Dates and times

Only events with both recorded start and end times use the timed grid. Unknown durations are not assigned an hour. All-day events, AM/PM notes and incomplete clock times remain above the grid with their recorded time information. Inclusive source end dates become exclusive widget end dates; the source records remain unchanged. Complete overnight/multi-day timed intervals retain their actual endpoints.

The timezone and caption come from `tzutil.LOCAL_TZ`, including `CSS_TZ_OFFSET` overrides. The default is Philippine time, UTC+08:00. Luxon renders those times consistently even when the browser uses another timezone. The initial day and today highlight follow the app's date. All 24 hours remain available by scrolling.

## Scope, fallback and limits

`calendar_routes.build_calendar_page` reads `office_calendar.items_between` for the current actor and selected scope, then applies the existing filters before building the snapshot. Schedule does not use the team-wide scope substitution used by the people Week view. The snapshot contains only title, dates/times, native URL, owner label, status and tone; notes, meeting URLs and people lists are excluded. There is no new API, cache, database schema, search index or service. Both page locations send `no-store`.

**Show weekly list** opens the complete native list and moves focus to its heading. That list works without JavaScript and remains available when the widget is unavailable. Printing uses the list. If more than **500** filtered items occur in the week, or an interval is invalid, the entire grid is withheld while the complete list remains readable. The grid never silently truncates a week. Long labels are compacted inside timed blocks; the full accessible label, tooltip and native list retain them.

Busy all-day rows use four visible levels with explicit **more** counts and a keyboard-openable popover. This keeps a day with many untimed imports from consuming the hourly viewport. The complete weekly list still includes every item.

All labels are text nodes, never staff-supplied HTML. Source destinations must be local paths. Static assets are locally vendored; the widget makes no external data, font or analytics requests. Existing destination routes recheck current access. This pilot sends no notifications.

## Dependency choice and provenance

FullCalendar **6.1.22 Standard**, its **6.1.22 Luxon3 adapter**, and **Luxon 3.7.2** are MIT licensed. The official Standard bundle also includes six FullCalendar modules and Preact **10.12.1**. All ten package versions, npm integrity receipts, licenses and hashes are recorded in [the manifest](dependencies/fullcalendar-manifest.json). The bundled Preact version is confirmed by the upstream `v6.1.22` pnpm lockfile.

Both FullCalendar 6.1.22 and 7.1.3 were published October 16, 2026. Version 7 was evaluated locally but its time-grid headers did not render visibly in the tested standalone browser setup; this pilot uses the maintained v6 distribution whose browser behavior passed the same probe. No v7 files or Temporal dependencies are shipped. The repository had 20,719 public stars at review; this is discovery context, not a quality guarantee.

The executable `fullcalendar-with-timezone.js` is exactly the three reviewed upstream scripts joined with newlines, in Luxon → FullCalendar → adapter order. Keeping the dependency chain in one file makes a blocked library load fall back without an adapter referencing a missing global. The vendor gate verifies both upstream files and exact derivation of the joined file. All licenses are retained under `static/vendor/fullcalendar/licenses/`. Premium Scheduler/resource code is excluded.

The release gate audits every bundled version against npm advisories and preserves its report with the dependency artifacts. The initial complete inventory had no reported advisories. There are no Python dependency changes or runtime CDN requirements.

## Verification

Domain/HTTP coverage checks real endpoints, inclusive dates, complete overnight times, unknown durations, timezone overrides, minimal fields, current-unit visibility, filters, preferred views, bounds, invalid dates, JSON escaping and no calendar writes. Chromium covers native links and keyboard focus, day selection, markup-safe labels, no-JavaScript/blocked-library fallback, and responsive geometry across 320–1920px and light/dark/contrast themes. Calendar agenda/month/people-week/timeline/home/filters/preferences/recurrence/room/API/guidance regressions remain required checks.

All fixtures are synthetic. Browser and mocked tests do not establish real production usage or notification delivery.

The shared test app recomputes import-time cookie security from each isolated test's environment. This prevents an earlier HTTPS-configured Telegram test from making a later HTTP preference client silently discard a Secure cookie. HTTP/HTTPS regressions retain the original preference assertions; production security and cookie middleware are unchanged.

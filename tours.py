"""Guided page tours — the SINGLE source for both the live coach-mark tour
(static/js/tour.js) and the written manual at /help.

Each key matches the `cur` page key derived in templates/dash_layout.html (which
itself comes from each route's `nav_active`). A tour is an ordered list of steps:

    {"target": "<css-selector>", "title": "<short>", "body": "<one or two plain sentences>"}

The matching element on the page must carry that selector (usually a
`data-tour="..."` attribute). A step whose target is absent for the current
user/role is skipped silently by tour.js — so manager-only steps never break a
staff member's tour. Keep tours short (3–6 steps) and write the body in plain
language, matching the CHANGELOG voice (no jargon).

`tour_for(key)` returns the list for a page (or [] when none) and is exposed as a
Jinja global so dash_layout.html can serve only the current page's tour. The full
TOURS dict is rendered, cap-filtered, by the /help manual.
"""

from __future__ import annotations

# Keyed by the dash_layout `cur` page key. Public/survey pages get no tours.
# Targets are plain CSS selectors resolved against the live page; most reuse an
# existing landmark class so no template markup was needed. A step whose target
# is absent (hidden by role, or no data yet) is skipped silently.
TOURS = {
    "home": [
        {"target": "[data-tour='search']",
         "title": "Find anything fast",
         "body": "Type an activity, a resource person, a report or a page here — or "
                 "press Ctrl-K (or tap the magnifier at the top) anywhere — to jump straight to it."},
        {"target": "[data-tour='period']",
         "title": "Pick a time window",
         "body": "These buttons set the period for the four summary figures below — "
                 "switch between all-time and the most recent windows."},
        {"target": "[data-tour='stats']",
         "title": "Your headline numbers",
         "body": "Responses received, people rated, overall satisfaction and how many "
                 "activities collected feedback — all for the window you chose above."},
        {"target": "[data-tour='modules']",
         "title": "Jump to your tools",
         "body": "Each card opens a part of the system — dashboards, reports, paper "
                 "entry and admin tools — showing only what your role can use."},
        {"target": "[data-tour='help']",
         "title": "Need a refresher?",
         "body": "Open this “?” any time to replay a page's tour, or open the full "
                 "written guide that collects every tour in one place."},
    ],
    "pulse": [
        {"target": ".scopebar",
         "title": "Set scope & period",
         "body": "Narrow everything on this page to a division or a time window — every "
                 "figure below updates to match."},
        {"target": ".winbar",
         "title": "Choose the window",
         "body": "Flip the vital signs between recent windows to see how the current "
                 "period compares with the one before."},
        {"target": ".pulse-grid",
         "title": "The three vital signs",
         "body": "Your headline service-quality measures, each with its status shown at "
                 "a glance so you can see what needs attention."},
        {"target": ".sum-grid",
         "title": "The supporting detail",
         "body": "A fuller breakdown sits below the vitals for when you need the numbers "
                 "behind the headline."},
    ],
    "people": [
        {"target": "h1.page",
         "title": "People",
         "body": "Everyone who has been rated — staff and resource persons — gathered in "
                 "one place."},
        {"target": ".scope-profile",
         "title": "The group's standing",
         "body": "A summary card for the current scope: the collective score and which "
                 "band it falls in."},
        {"target": ".searchbar",
         "title": "Find a person",
         "body": "Search by name to jump straight to someone's profile."},
        {"target": ".grid",
         "title": "Browse the cards",
         "body": "Each card is one person — open it for their full rating history and "
                 "coaching notes."},
    ],
    "teams": [
        {"target": "h1.page",
         "title": "Teams",
         "body": "How each organisational unit's activities are landing."},
        {"target": ".ucard",
         "title": "A unit at a glance",
         "body": "Each card shows a unit's score and how it's trending; open one to drill "
                 "into its sections."},
    ],
    "trends": [
        {"target": "h1.page",
         "title": "Trends",
         "body": "Movement over time — how the numbers are changing, not just where they "
                 "stand today."},
        {"target": ".tabs",
         "title": "Pick the survey type",
         "body": "Switch between walk-in, activity and resource-person trends."},
        {"target": ".panel.chart",
         "title": "Read the chart",
         "body": "Every chart has labelled axes and a note on how it's computed; hover "
                 "any point for the exact value and how it moved."},
    ],
    "participation": [
        {"target": "h1.page",
         "title": "Participation",
         "body": "Volume, coverage and blind spots — who is, and isn't, being reached."},
        {"target": ".vcards",
         "title": "Volume at a glance",
         "body": "Headline counts for responses and coverage within the current scope."},
        {"target": ".panel.chart",
         "title": "Response over time",
         "body": "See how participation rises and falls across periods."},
    ],
    "reports": [
        {"target": ".official",
         "title": "Official reports",
         "body": "These are the formal ARTA / SERVQUAL outputs you can read on screen or "
                 "download for submission."},
        {"target": ".rtabs",
         "title": "Switch report type",
         "body": "Move between the walk-in, activity and resource-person reports."},
        {"target": ".filters",
         "title": "Scope & period",
         "body": "Narrow the report to a unit and a date range before reading or "
                 "downloading it."},
    ],
    "verbatims": [
        {"target": "h1.page",
         "title": "Verbatims",
         "body": "What respondents actually wrote, in their own words."},
        {"target": ".pill-nav",
         "title": "Filter the source",
         "body": "Limit the comments to walk-in, activity or resource-person feedback."},
        {"target": ".vb-headline",
         "title": "The themes",
         "body": "A short summary of the recurring themes across all the comments."},
        {"target": ".vb-cols",
         "title": "Appreciated vs. to improve",
         "body": "Comments are sorted into what people valued and what they'd change — a "
                 "mixed comment appears under both."},
    ],
    "monitor": [
        {"target": "h1.page",
         "title": "Monitor",
         "body": "Track who registered and who has answered the survey, activity by "
                 "activity."},
        {"target": ".mon-list",
         "title": "Your activities",
         "body": "Each activity in its lifecycle — upcoming, ongoing, then recently "
                 "wrapped."},
        {"target": ".mon-card",
         "title": "Open one to track it",
         "body": "See the live count of who registered and who has completed the CSS."},
    ],
    "directory": [
        {"target": "h1.page",
         "title": "Directory",
         "body": "Your organisation's units, staff and resource persons — the backbone "
                 "the reports group everything by."},
        {"target": ".dcard",
         "title": "Work section by section",
         "body": "Set the bureau name, then build divisions, sections and people in order "
                 "down the page."},
    ],
    "create": [
        {"target": "h1.page",
         "title": "New survey",
         "body": "Set an activity's context once here, then generate the QR codes people "
                 "scan to rate it."},
        {"target": "fieldset",
         "title": "One step at a time",
         "body": "Work down the numbered sections — event type, the activity details, "
                 "then the QR options."},
        {"target": "button[type='submit']",
         "title": "Generate & save",
         "body": "Once the sections are filled in, this creates the activity and its QR "
                 "codes in one go."},
    ],
}


def tour_for(key):
    """The ordered steps for a page key, or [] when the page has no tour."""
    return TOURS.get(key or "", [])

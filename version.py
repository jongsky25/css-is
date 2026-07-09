"""Application version + plain-language changelog.

SINGLE SOURCE OF TRUTH for the version number shown on the sign-in screen.

────────────────────────────────────────────────────────────────────────
HOW TO BUMP (do this on EVERY push that changes what people see/use)
────────────────────────────────────────────────────────────────────────
1. Raise APP_VERSION by one step:
     • small change / fix .......... bump the minor:  1.1 → 1.2 → 1.3 …
     • big release / milestone ..... bump the major:  1.9 → 2.0
2. Prepend a NEW entry to the TOP of CHANGELOG (newest first) describing
   the change in LAYMAN terms — no jargon, written for the people who use
   the system, not for developers. Keep each bullet to one plain sentence.
3. Use a spelled-out date ("June 17, 2026").

The login page reads APP_VERSION and the newest CHANGELOG entry, so once you
edit this file the "What's new" note updates itself — nothing else to touch.
"""

APP_VERSION = "1.90"

# Newest first. CHANGELOG[0] is what the login screen highlights.
CHANGELOG = [
    {
        "version": "1.90",
        "date": "July 9, 2026",
        "summary": "The downloadable reports now list the written comments at the bottom, with repeats grouped into one line and a “×N” count instead of the same answer over and over.",
        "changes": [
            "At the foot of the downloadable customer-satisfaction reports, the "
            "comments people wrote are now listed together. Identical answers are "
            "shown once with a “×N” next to them — so a repeated “Very helpful "
            "staff” shows as “Very helpful staff ×3” instead of the same comment "
            "printed again and again. Empty and throw-away answers (“none”, “n/a”, "
            "“wala”, and the like) are left out, so the list carries only real "
            "feedback.",
            "The Word walk-in (ARTA) report lists them grouped as Appreciated, To "
            "improve, and Other; the Word resource-person (SERVQUAL) report gains a "
            "new “Respondent comments” section it didn't have before; and the "
            "resource-person Excel gets a tidy “Comments” sheet with each distinct "
            "comment and how many people gave it, next to the existing "
            "one-row-per-person sheet.",
            "The PDF and slide versions still show just a few of the most common "
            "comments as a taste, but now mark repeats with “×N” too and point to "
            "the Word file for the complete list. Very long comment lists are "
            "capped with an “…and N more” note so a report never runs to hundreds "
            "of pages.",
        ],
    },
    {
        "version": "1.89",
        "date": "July 9, 2026",
        "summary": "Two labels now read more plainly: an “activity report” is now called a “customer satisfaction survey report,” and the “Verdict” column is now titled “Interpretation.”",
        "changes": [
            "Wherever the per-activity report was called an “activity report” — the "
            "report’s title, the “View individual reports” link, and the downloadable "
            "Word, Excel, PDF and PowerPoint versions — it is now called the "
            "“Customer Satisfaction Survey Report.”",
            "The service-quality table column that read “Verdict” (how each dimension "
            "landed against what people expected) is now headed “Interpretation,” on "
            "screen and in every download, along with the matching wording on the "
            "activity, team and dashboard cards.",
            "These are wording changes only — the scores, the way they are worked out, "
            "and the saved responses are all exactly the same.",
        ],
    },
    {
        "version": "1.88",
        "date": "July 9, 2026",
        "summary": "An activity you close now leaves the home “Ongoing” list right away, instead of lingering there for hours.",
        "changes": [
            "When you closed an activity, the home dashboard could keep showing it "
            "under “Ongoing — CSS collecting” long after — sometimes until the next "
            "day — even though its reporting was already closed. The dashboard was "
            "reading the wrong clock (the server's, which runs on a different time "
            "zone) to decide whether an activity was still collecting. It now uses "
            "the same Philippine-time clock as the rest of the app, so a closed "
            "activity drops off the Ongoing list the moment you close it. (The "
            "public response link itself was always closing on time; only the "
            "dashboard label lingered.)",
        ],
    },
    {
        "version": "1.87",
        "date": "July 9, 2026",
        "summary": "Fixed a problem where an activity's newly encoded responses could disappear from its reports — the count showed on the Manage page, but the resource-person report came up empty and the activity was missing from the report's activity list.",
        "changes": [
            "For one invited activity, the Manage page correctly showed its 286 "
            "responses, but opening “View resource-person results” said there were "
            "none, the responses didn't appear in the Resource Persons report, and "
            "the activity was missing from that report's activity picker. The "
            "answers were safe in the database the whole time — they had slipped "
            "out of the app's fast in-memory copy that the reports read from, "
            "during a busy live-encoding session, and stayed out. The reports now "
            "keep that fast copy exactly in step with what's saved, so freshly "
            "encoded responses always show up, and any activity affected before "
            "this fix is restored automatically.",
        ],
    },
    {
        "version": "1.86",
        "date": "July 6, 2026",
        "summary": "An invited (“we were invited / outside”) activity now stays on the home “Ongoing” list for as long as its combined-QR form is still open, so you can always find and manage it.",
        "changes": [
            "Invited activities — the ones where your office was a guest and you "
            "gather feedback through a single combined-QR link — used to drop off "
            "the home page about a week after the event, even when the link was "
            "still live and collecting answers. They never appeared under "
            "“Upcoming” or “Ongoing”, only briefly under “Your recent activities”, "
            "so an older-but-still-open one became impossible to reach. Now any "
            "invited activity whose feedback window is still open shows under "
            "“Ongoing — CSS collecting”, with its name, its running response count, "
            "and a link straight to its Manage page. It leaves the list once you "
            "close its window.",
        ],
    },
    {
        "version": "1.85",
        "date": "July 6, 2026",
        "summary": "On an activity's Monitor page, you can now click a participant's status to open their own answers — the exact ratings and comments they gave.",
        "changes": [
            "On the Monitor page for an activity, each participant who has "
            "answered now has a clickable status. Open it to see that person's "
            "own response — their rating for every question, any note they left "
            "on a question, and their overall comment, shown just as they "
            "answered. Only the activity's creator or an admin can open it. It "
            "covers people who registered and answered through the activity "
            "link; anonymous walk-in / QR / paper responses aren't tied to a "
            "name, so they don't appear here. If someone's personal details "
            "were removed under the data-retention policy, their row shows as "
            "“identity removed” with no answers.",
        ],
    },
    {
        "version": "1.84",
        "date": "July 6, 2026",
        "summary": "The Verbatims page now shows a third “Mixed” column, so good-and-bad comments have a home of their own instead of appearing on both sides.",
        "changes": [
            "On Reports → Verbatims, comments used to sit in two columns — what "
            "people appreciated and what they'd improve — and a “Mixed” comment "
            "(one that names a strength and a wish in the same breath) was shown "
            "in both. There's now a dedicated third “Mixed — good and bad” column, "
            "so each comment appears once, in the column that fits it. Re-tagging a "
            "comment still works the same way; a Mixed one simply moves to its own "
            "column now.",
        ],
    },
    {
        "version": "1.83",
        "date": "July 6, 2026",
        "summary": "The Resource Persons Excel download now includes a per-respondent “Responses” sheet — the actual scores behind each activity's numbers.",
        "changes": [
            "When you download the Excel (.xlsx) from Reports → Resource Persons, "
            "there's a new “Responses” sheet listing one row per person who "
            "answered — each respondent's own scores for the five service "
            "dimensions, their overall, their expectation and overall-service-"
            "quality ratings, plus when they answered, the activity, and any "
            "comment they left. It follows whatever activity you've filtered to, "
            "so you can pull the raw, per-submission data for a single activity or "
            "resource person instead of only the combined averages. The other "
            "sheets and all the report documents are unchanged.",
        ],
    },
    {
        "version": "1.82",
        "date": "July 5, 2026",
        "summary": "Fixed the automatic scheduled backup so it actually runs — it was switched on but silently never firing.",
        "changes": [
            "The Backups page's automatic schedule was turned on but had never "
            "actually run a single backup, because it was waiting on a starting "
            "point it could never set for itself. It now seeds that starting point "
            "when the schedule is on, so the daily backup fires as intended — and if "
            "the system happens to be paused at the scheduled time, it catches up the "
            "next time someone opens it, instead of skipping the day. Your data was "
            "never at risk in the meantime: the system already saves a copy to "
            "permanent storage continuously, and the new daily off-site copy on "
            "GitHub was unaffected.",
        ],
    },
    {
        "version": "1.81",
        "date": "July 5, 2026",
        "summary": "The Monitor page now has a “What people said” button that takes you straight to the written comments for that activity.",
        "changes": [
            "An activity's Monitor page now shows a “💬 What people said →” button "
            "that opens the comments people left, jumping straight to the "
            "“In people's own words” section of that activity's report. It works for "
            "both your own activities and invited (resource-person) ones, and only "
            "appears once at least one response has come in — so you can read the "
            "feedback in words without hunting through the reports for it.",
        ],
    },
    {
        "version": "1.80",
        "date": "July 5, 2026",
        "summary": "The Backups page now shows a history of the daily off-site backups kept safely on GitHub — so you can confirm at a glance that a recent copy exists off Hugging Face.",
        "changes": [
            "The Backups page has a new “Off-site backups (GitHub)” panel. A separate "
            "job now runs every day on GitHub — not on any office computer — and pulls "
            "an encrypted copy of the whole database into a private GitHub repository, "
            "so a recent copy survives even if Hugging Face itself were lost. Each time "
            "it succeeds it reports back here, and the panel lists the recent copies with "
            "the date and file name, plus a green “Off-site copy current” badge.",
            "If no off-site backup has reported in for more than two days, the panel "
            "shows an amber “overdue” warning pointing you to the GitHub job — so a "
            "silently broken backup can't go unnoticed. This replaces the old daily "
            "backup that only ran when a particular office PC happened to be switched on.",
        ],
    },
    {
        "version": "1.79",
        "date": "July 5, 2026",
        "summary": "Closing an activity now moves it to “Recently concluded” right away, and an invited activity's written comments now show on its results page.",
        "changes": [
            "When you close an activity, it now appears in the home page's "
            "“Recently concluded” list straight away — including a one-day activity "
            "you close on the same day, and activities with no end date set. Before, "
            "the list only went by the date, so a just-closed activity could stay off "
            "it until the next day (or never show, if it had no end date).",
            "An invited / resource-person activity now shows the written comments "
            "people left right on its results page (Resource Persons report, narrowed "
            "to that activity) — the same “In people's own words” section your own "
            "activities already have, with a “See this activity's verbatims” link that "
            "stays focused on just that activity. These activities had no comments view "
            "of their own before.",
            "Fixed a case where opening one invited activity's results could quietly "
            "show the whole bureau's numbers instead when the activity couldn't be "
            "matched — it now shows a clear, empty result for that activity rather than "
            "misleading figures.",
        ],
    },
    {
        "version": "1.78",
        "date": "July 2, 2026",
        "summary": "Once you close an activity, its report is one click away, right on the Manage page.",
        "changes": [
            "When an activity is closed, its Manage page now shows a prominent "
            "“View the report →” button next to Reopen — so closing an activity "
            "leads straight to its results instead of a dead end. The button opens "
            "the right report for the activity: the per-activity SERVQUAL report "
            "for a regular activity, or the Resource Persons results for an "
            "invited / resource-person one. (Invited activities already had this; "
            "now regular ones do too.)",
        ],
    },
    {
        "version": "1.77",
        "date": "July 2, 2026",
        "summary": "Resource-person results are one click from the home page, the Resource Persons report has an Excel download, and you can remove a stray registration.",
        "changes": [
            "On the home page's “Recently concluded” list, an invited / "
            "resource-person activity now opens its actual results (the Resource "
            "Persons report, narrowed to that activity) instead of a generic list "
            "— so “open the report” finally lands on the numbers.",
            "The Resource Persons report (Reports → Resource Persons) now has an "
            "Excel (.xlsx) download under “Raw data”, alongside the Word / PDF / "
            "PowerPoint options — the dimension scores, the SERVQUAL summary and "
            "the respondent profile in a spreadsheet you can work with.",
            "On an activity's Monitor page you can now remove a registrant entry "
            "that was a test, a duplicate, or a no-show — each roster row has a "
            "“Remove” button (with a confirm). For safety this is only offered "
            "before that person has answered: once an entry has ratings they're "
            "part of the reports, so it can't be deleted.",
        ],
    },
    {
        "version": "1.76",
        "date": "July 2, 2026",
        "summary": "Close a survey the moment you're done — and see at a glance when each survey stops accepting answers.",
        "changes": [
            "You can now stop a survey right away, without waiting for its "
            "“closes” date to arrive. Open the activity's Manage page and use "
            "“Close survey now” — it immediately stops new answers on both the "
            "public link and paper entry. Everything already collected stays in "
            "your reports, and you can reopen it any time to back-enter a late "
            "form or fix a typo, then close it again. This used to be available "
            "only for invited (“outside”) activities; now every activity has it.",
            "The Monitor page for an activity now shows, right under the title, "
            "whether it's still open and until when — “Open until December 31, "
            "2099”, “Open — no closing date set”, or “Closed”. No need to dig into "
            "the Manage page to check.",
        ],
    },
    {
        "version": "1.75",
        "date": "June 30, 2026",
        "summary": "The comment raffle now works for online activities too — not just face-to-face ones.",
        "changes": [
            "You can now run the comment raffle at an online activity, exactly like "
            "a face-to-face one. Anyone who leaves a comment on an online activity's "
            "feedback now gets a claim code on their thank-you screen and is entered "
            "in the draw; before, online responses were quietly left out. When you "
            "draw a winner, an online entrant is identified by their claim code — "
            "they show it to you or paste it in the chat to claim the prize — just "
            "like an anonymous walk-in. Nothing changes for face-to-face activities; "
            "this simply removes the face-to-face-only limit.",
        ],
    },
    {
        "version": "1.74",
        "date": "June 30, 2026",
        "summary": "Archive an activity straight from the home page's “Ongoing” list — no more hunting for where to put away a test or stray activity.",
        "changes": [
            "Admins now get an “Archive” button on each activity in the home "
            "page's “Ongoing — CSS collecting” list, so a test run or a stray "
            "activity that's still collecting can be put away right where you spot "
            "it — instead of going to the Edit / merge page to find the control. "
            "It works for both kinds the list shows: a one-off speaker review "
            "archives on its own, and a full event archives the whole activity "
            "(the event review and all its speaker forms) in one go. Nothing is "
            "deleted — every archived activity drops out of all lists, feeds and "
            "reports, and an admin can restore it any time from “Archived "
            "activities”.",
        ],
    },
    {
        "version": "1.73",
        "date": "June 26, 2026",
        "summary": "Safety net: the system now notices and warns within minutes if it ever stops saving your data — and can no longer get stuck doing so silently.",
        "changes": [
            "Hardened how the app saves live data to permanent storage. The "
            "background saver can no longer get silently stuck: each save now has "
            "a time limit, so a slow or stalled storage connection is abandoned "
            "and reported instead of freezing the saver. And the “is your data "
            "being saved?” line on the Operations page now turns red within a few "
            "minutes if saving has actually stopped — previously it could keep "
            "showing green while nothing was being saved. No action needed; this "
            "is purely a reliability and early-warning improvement.",
        ],
    },
    {
        "version": "1.72",
        "date": "June 26, 2026",
        "summary": "The Activity filter on the Resource Persons report is now a search box — type to find an activity instead of scrolling.",
        "changes": [
            "The “Activity” filter on the Resource Persons report is now a "
            "search-as-you-type box: click it and start typing an activity name "
            "to jump straight to it, instead of scrolling a long list. Use the "
            "up/down arrows and Enter to pick one from the keyboard. The list "
            "now stays a tidy, fixed width with longer titles trimmed, so it "
            "never runs off the side of the page. If a browser has scripting "
            "turned off it quietly falls back to the ordinary dropdown.",
        ],
    },
    {
        "version": "1.71",
        "date": "June 26, 2026",
        "summary": "Fixed the Activity dropdown on the Resource Persons report stretching too wide.",
        "changes": [
            "On the Resource Persons report, the new “Activity” filter sized itself "
            "to its longest activity title, so once you picked one it stretched "
            "almost the full width of the page. It now stays a sensible, compact "
            "width like the Scope and Period filters beside it, with longer titles "
            "trimmed inside the box.",
        ],
    },
    {
        "version": "1.70",
        "date": "June 25, 2026",
        "summary": "The shortcut cards on the home page now point to everything the system can do — including the newer pages.",
        "changes": [
            "The shortcut cards at the bottom of the home page had fallen behind as "
            "new pages were added, so a few things were only reachable from the top "
            "menu or the search box. They now list them all: “See how we're doing” "
            "adds Teams and Participation; “Official reports” adds the Resource "
            "Persons report and Shared materials; “Run a survey” adds the Monitor and "
            "the Invited events list; and Administration adds Sharing and the user "
            "Feedback board. Each shortcut still only shows to people whose role can "
            "open it.",
        ],
    },
    {
        "version": "1.69",
        "date": "June 25, 2026",
        "summary": "One click from an invited activity to its resource-person results — plus a fix so an activity report never breaks on a half-finished response.",
        "changes": [
            "Invited (outside) activities now have a direct “View resource-person "
            "results” link — on the new Invited events page and on the activity's own "
            "manage page. Because these activities are scored per resource person (they "
            "have no separate event report), the link opens the Resource Persons report "
            "already narrowed to just that activity, so you can see how the speakers did "
            "in one step instead of hunting for it. The link appears once an activity has "
            "responses; the manage page's old “View report” button used to lead to a "
            "page that didn't exist for these activities, and now points to the right place.",
            "Fixed a case where an activity's report page could fail to load if someone "
            "had submitted feedback only part-way (rating the event but skipping the "
            "“what did you expect” question). That dimension now simply shows a dash "
            "instead of a score gap, and the report opens normally.",
        ],
    },
    {
        "version": "1.68",
        "date": "June 25, 2026",
        "summary": "Invited (outside) activities are easier to find — a new list of them all, and they now show up on the home page after they finish.",
        "changes": [
            "A new “Invited events” page (under Manage) lists every activity run by "
            "an outside body where your staff were resource persons — upcoming, "
            "ongoing and finished, all in one place. Before, once an invited activity "
            "wrapped up it dropped off the Monitor and was only findable by digging "
            "through the reports; now it always has a home, and you can reach it from "
            "the menu or the search box. The Monitor's invited section also links "
            "straight to it for the ones that have concluded.",
            "The home page's “Recently concluded” strip now includes invited "
            "activities too, not just bureau events — so a just-finished invited "
            "session shows up there like everything else, marked with an “Invited” "
            "tag and linking to the invited-events list. Invited activities in your "
            "“Your recent activities” strip now carry the same “Invited” tag, so "
            "they're easy to tell apart from bureau-run ones at a glance.",
        ],
    },
    {
        "version": "1.67",
        "date": "June 25, 2026",
        "summary": "The Audit log now reads in plain English, with a quick look at what's been happening lately.",
        "changes": [
            "Every row in the Audit log now shows a plain-English action instead of "
            "a technical code — “Signed in”, “Updated feedback status”, “Set an "
            "activity's response window”, and so on — colour-grouped by kind "
            "(sign-ins, accounts, activities, feedback, data & backups). The exact "
            "technical code is still there if you hover over the label, and the "
            "filter dropdown now lists the friendly names too.",
            "A new “What's been happening” panel sums up the last 7 days: which "
            "kinds of action came up most (with a little bar for each) and who's "
            "been the busiest — so you get the shape of recent activity at a glance, "
            "on top of the existing today / this-week / all-time counts.",
        ],
    },
    {
        "version": "1.66",
        "date": "June 25, 2026",
        "summary": "The System health page now shows who's using the app and what's happened lately, in plain numbers.",
        "changes": [
            "The System health page has two new panels. “Who's using it” shows how "
            "many staff are active right now (anyone who did something in the last "
            "15 minutes), how many different people have signed in today and over "
            "the last 7 days, who signed in most recently, and a short list of the "
            "latest sign-ins — so you can see at a glance who's on the system.",
            "“Lately” shows what's moved in the last 7 days — feedback received "
            "today and this week, activities set up this week, and new participants "
            "registered this week — alongside the existing all-time totals, so the "
            "page reflects what's happening now and not just lifetime counts.",
        ],
    },
    {
        "version": "1.65",
        "date": "June 25, 2026",
        "summary": "Narrow the Resource Persons report to a single activity with a new Activity filter.",
        "changes": [
            "The Resource Persons report (Reports → Resource Persons) now has an "
            "“Activity” dropdown next to Scope and Period. Pick an activity and the "
            "whole report — the scores, dimensions and respondent count — narrows to "
            "just that activity's resource-person responses, so you can quickly pull "
            "up and review one activity on its own. Leave it on “All activities” to "
            "see everything combined as before. The downloads (Word, PDF, PowerPoint) "
            "follow the chosen activity too.",
        ],
    },
    {
        "version": "1.64",
        "date": "June 25, 2026",
        "summary": "Fixed the Activities list on a phone — turning on “Edit / merge” no longer hides the list behind the actions panel.",
        "changes": [
            "On the Activities list, switching on “Edit / merge” opens a panel of "
            "actions (rename, re-file, export, archive) that stays pinned to the "
            "bottom of the screen. On a phone that panel grew so tall it covered the "
            "whole activity list, so you couldn't see or tick anything. It now takes "
            "up at most half the screen and scrolls on its own, leaving the list "
            "visible above it — and its labels and boxes now stack full-width so "
            "they're no longer squeezed into a narrow column.",
        ],
    },
    {
        "version": "1.63",
        "date": "June 25, 2026",
        "summary": "A safeguard so automatic saving can recover on its own if it ever gets stuck — and the System health page now tells you, in plain words, whether your data is being saved right now.",
        "changes": [
            "We fixed a rare condition where the system's automatic save to "
            "permanent storage could get stuck and quietly stop saving new entries "
            "— the cause of some entries being lost on June 24. The system now "
            "recognises when this safety check has wedged itself for no good reason "
            "and clears it automatically, so saving resumes on its own within about "
            "a minute instead of staying stuck.",
            "The System health page now shows, in everyday words, whether your live "
            "data is actually being saved to permanent storage at that moment — with "
            "a clear red warning if it ever isn't — so this kind of problem can be "
            "spotted right away instead of going unnoticed.",
        ],
    },
    {
        "version": "1.62",
        "date": "June 25, 2026",
        "summary": "Closing an invited activity now really closes it — no more entries, its details lock, and a report is one click away.",
        "changes": [
            "On an invited (outside) activity's manage page, “Close responses now” "
            "now does what it says: it stops new answers on every speaker review — "
            "on paper as well as through the online link — instead of only the "
            "online link. A closed activity also disappears from the paper-entry "
            "list, so no one can key in more slips for it by mistake.",
            "Once an activity is closed, its details on that page (speakers, dates, "
            "the open/close window and the raffle) are locked and clearly marked, so "
            "a finished activity can't be edited by accident. A “Reopen to make a "
            "correction” button brings it all back if you need to fix a typo or "
            "back-enter a late form — then you simply close it again.",
            "Closing now also surfaces a “View activity report →” link right at the "
            "top of the page, so the report for that activity is one click away the "
            "moment you wrap it up. Nothing is ever deleted — a closed activity "
            "stays in all your reports.",
        ],
    },
    {
        "version": "1.61",
        "date": "June 23, 2026",
        "summary": "A stronger safeguard against a restart quietly rolling back very recent changes.",
        "changes": [
            "We closed a rare but real way the system could lose a few minutes of "
            "recent work. When the app restarts, it restores your data from the "
            "permanent storage; on a busy hand-off the storage can briefly show an "
            "out-of-date list, and the app could pick up an older copy and then save "
            "that back — quietly undoing the newest changes. (This is what briefly "
            "dropped three pieces of feedback overnight; no survey responses were "
            "affected, and the three were restored.)",
            "The app now stamps a “high-water mark” every time it saves, so on "
            "restart it refuses to load a copy that's older than what it already "
            "knows exists — it waits for the storage to catch up, and a container "
            "that finds itself on a stale copy will not overwrite the good backups. "
            "Nothing changes in how you use the system; it's purely a durability "
            "safeguard behind the scenes.",
        ],
    },
    {
        "version": "1.60",
        "date": "June 23, 2026",
        "summary": "The System health and Audit log pages now open with plain-language summaries — what's in the system, and what the log has been recording.",
        "changes": [
            "The System health page has a new “What's in the system” panel with "
            "everyday totals at a glance: how many staff accounts are signing in, "
            "how many people are in the directory, how many activities have been set "
            "up, how many participants have registered, and how much feedback has "
            "been collected — alongside the existing “is it healthy and fast” cards.",
            "The Audit log page now opens with an “At a glance” summary: how many "
            "actions were recorded today and in the last 7 days, the total on file, "
            "who's been the busiest this week, the most common kind of action, and "
            "what the most recent action was — so you get the shape of the activity "
            "before scrolling the full list.",
        ],
    },
    {
        "version": "1.59",
        "date": "June 23, 2026",
        "summary": "Fixed a person's page and downloads breaking when a period had activity but no score yet.",
        "changes": [
            "A staff member's “Scores over time” chart could fail to load — both on "
            "their page and in the image/PDF downloads — if one of the periods had "
            "an engagement recorded but no ratable score yet (for example, all "
            "answers left as “not applicable”). Such a period now simply shows as a "
            "gap with a “—” instead of stopping the whole chart from drawing.",
        ],
    },
    {
        "version": "1.58",
        "date": "June 23, 2026",
        "summary": "Each registered participant now answers a feedback form once — already-answered forms show as done.",
        "changes": [
            "On an activity's feedback page, any survey a registered participant has "
            "already answered now shows with a green “✓ Done” mark and can't be opened "
            "again — so the same person can't accidentally rate the same speaker or "
            "event twice (from a double-tap, the back button, or re-opening their "
            "link). Once they've answered everything, a short “you've answered all the "
            "feedback” note appears. Walk-in and anonymous responses on a shared device "
            "are unaffected — those still get a fresh form each time.",
        ],
    },
    {
        "version": "1.57",
        "date": "June 23, 2026",
        "summary": "Quickly find a staff member on the Users & roles page with a new search box.",
        "changes": [
            "The Users & roles page now has a search box above the staff list. Start "
            "typing a name, email or section and the list narrows to just the matching "
            "people as you type — handy once you have more staff than fit on one screen. "
            "Clear the box to see everyone again.",
        ],
    },
    {
        "version": "1.56",
        "date": "June 22, 2026",
        "summary": "Spot Feedback can now be reviewed faster behind the scenes, so replies and fixes come back to you sooner.",
        "changes": [
            "Admins who handle Spot Feedback now have a quicker way to pull up the "
            "current list of submissions and their replies, without exporting a file "
            "each time. Nothing changes in how you send feedback or see updates — "
            "this just shortens the loop between you flagging something and the team "
            "acting on it.",
        ],
    },
    {
        "version": "1.55",
        "date": "June 22, 2026",
        "summary": "A stronger safeguard so a restart can never quietly bring back old data.",
        "changes": [
            "We fixed the cause of a recent incident where the system briefly came "
            "back showing older information after a restart. The permanent storage "
            "the app saves to can take a few seconds to connect when the system "
            "starts up; if the app didn't wait, it mistook “not ready yet” for "
            "“nothing saved” and fell back to a built-in starter copy.",
            "Now, on every start the app first confirms the permanent storage is "
            "really connected and waits for it, and it will refuse to start on the "
            "old starter copy rather than show you stale data — so a slow "
            "connection self-corrects on the next start instead of losing recent "
            "work.",
            "It also now keeps a daily safety copy going back two weeks, on top of "
            "the frequent ones, so there's always a recent point to restore from.",
        ],
    },
    {
        "version": "1.54",
        "date": "June 22, 2026",
        "summary": "Event dates now read in plain words (no more day/month mix-ups), and a bureau activity can be saved without a resource person.",
        "changes": [
            "Every date you pick now shows in plain words — “22 Jun 2026”, with the "
            "full “Monday, 22 June 2026” spelled out underneath on the create form. "
            "Before, the date box followed your computer's region setting, so on some "
            "desktops it read 06/22 (month first) and on others 22/06 (day first), "
            "which was easy to misread. The calendar still works the same; only how "
            "the date is shown changed.",
            "When you set up a bureau-organized activity that had no resource person "
            "(a consultation, a service day, an internal activity), you can now leave "
            "the resource-person section empty — you'll still get the event review. "
            "Outside events we were invited to still need at least one resource person.",
        ],
    },
    {
        "version": "1.53",
        "date": "June 22, 2026",
        "summary": "The hidden data tables for screen readers now cover the Pulse, Participation and Written-comments charts too.",
        "changes": [
            "Following last update's Trends charts, every chart on the Pulse, "
            "Participation and Written-comments pages now also has a matching data "
            "table that's hidden on screen but read out by screen readers — so the "
            "exact figure behind each line is available to someone who can't see it. "
            "The tone-of-comments chart reads out all three shares (appreciation, "
            "areas to improve, and mixed) for each period.",
        ],
    },
    {
        "version": "1.52",
        "date": "June 22, 2026",
        "summary": "Keyboard users can skip straight to the page content, and every Trends chart now carries a hidden data table for screen readers.",
        "changes": [
            "A “Skip to content” link now appears the moment you press Tab on any "
            "page — press Enter and you jump past the menu straight to the main "
            "content, instead of tabbing through every menu item first. It stays "
            "out of sight until you need it.",
            "Every chart on the Trends page now has a matching data table that's "
            "hidden on screen but read out by screen readers, so someone who can't "
            "see the lines can still hear the exact figure for each period. (The "
            "other dashboard charts get the same treatment next.)",
        ],
    },
    {
        "version": "1.51",
        "date": "June 22, 2026",
        "summary": "Changing a staff member's email in the Directory now also updates the email they sign in with.",
        "changes": [
            "When you edit a staff member's email in the Directory, that change now "
            "carries over to their account too — so they sign in with the new email, "
            "and resetting or reactivating their account uses it as well. Until now "
            "the account quietly kept the old email, so it looked like your change "
            "had reverted. If the new email already belongs to someone else's "
            "account, the Directory still saves but the sign-in email is left "
            "unchanged, with a note explaining why.",
        ],
    },
    {
        "version": "1.50",
        "date": "June 22, 2026",
        "summary": "A new duck-race draw for the comment raffle, and certificates are now signed only by the bureau's chiefs and director.",
        "changes": [
            "The comment-raffle draw screen has a new animation to choose from: a "
            "“Duck race”. Pick it and the entries line up as rubber ducks paddling "
            "across a pond — the winner's duck pulls ahead for a photo finish — "
            "alongside the existing slot machine, prize wheel, name shuffle and "
            "lottery tumbler, with the same sound effects and confetti.",
            "When you set up a Certificate of Appearance, the “Signed by” list now "
            "offers only the people who actually sign them — Section Chiefs, "
            "Division Chiefs and the Director — instead of the whole directory, so "
            "you don't have to scroll past everyone else or keep a signature on "
            "file for staff who never sign. If an activity was already set to "
            "someone outside that list, it keeps that choice until you change it.",
        ],
    },
    {
        "version": "1.49",
        "date": "June 22, 2026",
        "summary": "Set a start-and-end date for multi-day activities, and the Certificate of Appearance is now PDF-only.",
        "changes": [
            "When you create an activity you can now give it an end date as well as "
            "a start date — for anything that runs more than one day (a three-day "
            "training, say). Leave the end date blank and it stays a single-day "
            "activity, exactly as before. The activity then shows its full run "
            "everywhere — “June 16–18, 2026” — on the sign-in page, the survey, the "
            "monitor, and the certificate.",
            "You can also fix or change an activity's dates after it's created: open "
            "its manage page and use the new “Activity dates” box. The reporting "
            "period still follows the start date, so reports keep counting the "
            "activity in the right quarter and year.",
            "The Certificate of Appearance now downloads as a PDF only. The editable "
            "PowerPoint version has been removed, so an official certificate can't be "
            "altered after it's issued.",
        ],
    },
    {
        "version": "1.48",
        "date": "June 22, 2026",
        "summary": "See how the tone of written comments has shifted over time.",
        "changes": [
            "The Written Comments page now opens with a “Tone of comments over "
            "time” chart. For each period it shows what share of comments read as "
            "appreciation, as something to improve, or as mixed (a good point and "
            "a gripe in one) — three lines that always add up to 100%, so you can "
            "see at a glance whether feedback is warming or cooling. A short "
            "plain-language line sums up the shift, and you can switch between "
            "monthly, quarterly and yearly.",
            "The same chart now appears in the page's PDF and PowerPoint "
            "downloads, with labelled axes and a caption, so it's ready to drop "
            "into a report.",
        ],
    },
    {
        "version": "1.47",
        "date": "June 22, 2026",
        "summary": "Run a comment raffle at face-to-face activities — draw a random winner on a big screen.",
        "changes": [
            "On any activity's manage page you can now switch on a “Comment "
            "raffle”. Once it's on, anyone who leaves a comment when they answer "
            "the feedback gets a short claim code on their thank-you screen — their "
            "ticket to a prize.",
            "When it's time to draw, open the full-screen draw page and pick a "
            "random winner with a bit of show: choose between a slot machine, a "
            "spinning prize wheel, a name shuffle, or a lottery tumbler — each with "
            "optional sound effects and confetti. You can draw again for more "
            "prizes, and past winners aren't drawn twice.",
            "It works for both your own activities and invited (outside) ones. For "
            "registered participants the winner's name shows on screen; for "
            "anonymous responses the winner is identified by their claim code, which "
            "they show you to collect the prize. Only face-to-face responses are "
            "entered.",
        ],
    },
    {
        "version": "1.46",
        "date": "June 21, 2026",
        "summary": "Export several activities at once, and restore several archived ones together.",
        "changes": [
            "On the activities list, click “Edit / merge”, tick the activities you "
            "want, and a new “Export selected” button downloads just those activities "
            "as a spreadsheet — handy for pulling together a report on a specific set "
            "of activities without exporting the whole list.",
            "The “Archived activities” page now has a “Select to restore” mode: tick "
            "several put-away activities and bring them all back in one click, instead "
            "of restoring them one at a time.",
        ],
    },
    {
        "version": "1.45",
        "date": "June 21, 2026",
        "summary": "Guided tours — a short, skippable walk-through of each page, plus a full written guide.",
        "changes": [
            "The first time you open a page, a short guided tour now points out the "
            "main things on it — one tip at a time, with Back, Next and Skip. It "
            "shows once per page; close it and it won't pop up again.",
            "A new “?” button at the top-right of every page lets you replay that "
            "page's tour whenever you like, or open the full written guide — a single "
            "searchable page that collects every page's walk-through in one place.",
        ],
    },
    {
        "version": "1.44",
        "date": "June 21, 2026",
        "summary": "Small accessibility and dark-mode fixes on the survey forms.",
        "changes": [
            "The optional “add a note” boxes under each survey question now carry "
            "a proper label, so people using a screen reader know what the box is "
            "for.",
            "The one-question-at-a-time view's “please answer first” warning used a "
            "fixed red that was hard to read in dark mode; it now follows your "
            "chosen theme.",
        ],
    },
    {
        "version": "1.43",
        "date": "June 21, 2026",
        "summary": "Admin pages read better on phones and in dark mode.",
        "changes": [
            "Tables on the Backups and Paper-entry pages, and the resource and "
            "speaker lists on the activity-management pages, now stack or scroll "
            "neatly on a narrow phone screen instead of running off the edge.",
            "A few faint colours on the Backups and Directory pages (a status "
            "chip and a delete-button outline) used to stay light grey in dark "
            "mode; they now follow whichever theme you've chosen.",
            "The small decorative icons on the Directory, System-health and Audit "
            "pages are now skipped by screen readers, and the disabled-remove "
            "padlock on the invited-activity page now announces what it means.",
        ],
    },
    {
        "version": "1.42",
        "date": "June 21, 2026",
        "summary": "Dark-mode and narrow-screen fixes on the official Reports page.",
        "changes": [
            "On the official Reports page, the neutral middle section of the "
            "answer-distribution bars and a couple of faint table lines used to "
            "stay light grey even in dark mode, where they glared against the dark "
            "background. They now follow whichever theme you've chosen.",
            "The small breakdown tables on that page (the respondent profile and "
            "the Citizen's Charter details) now scroll neatly on a narrow phone "
            "screen instead of being cut off at the edge.",
        ],
    },
    {
        "version": "1.41",
        "date": "June 21, 2026",
        "summary": "Tidier “nothing here yet” notes on an activity's report page.",
        "changes": [
            "On a single activity's report, the spots that say there's nothing to "
            "show yet — no demographic breakdown, no service-quality scores, or no "
            "other activities to compare against — now use the same tidy little "
            "message as the rest of the dashboard, instead of a bare line of text, "
            "so it's clear nothing is broken.",
        ],
    },
    {
        "version": "1.40",
        "date": "June 21, 2026",
        "summary": "Charts on the Trends and Participation pages now read correctly in dark mode.",
        "changes": [
            "On the Trends and Participation pages, the faint gridlines, the shaded "
            "“normal range” bands behind the charts, the progress bars and their "
            "small colour keys used to stay light-grey even in dark mode, where "
            "they glared against the dark background. They now follow whichever "
            "theme you've chosen — light, dark, or high-contrast — so the figures "
            "look right everywhere.",
            "Two faint chart labels on the Trends page (the axis titles and the "
            "“how it's computed” note) were too dark to read in dark mode; they now "
            "use the same readable shade as the rest of the page.",
        ],
    },
    {
        "version": "1.39",
        "date": "June 21, 2026",
        "summary": "Screen-reader cleanups on the Teams, Trends and Participation pages.",
        "changes": [
            "The little decorative icons and arrows on the Teams, Trends and "
            "Participation pages are now skipped by screen readers, so they no "
            "longer interrupt the reading of a unit's name or a figure with stray "
            "symbols.",
            "A unit's coaching page with no rated activities yet now shows the same "
            "tidy “nothing here yet” message as the rest of the dashboard, instead "
            "of a bare line of text.",
        ],
    },
    {
        "version": "1.38",
        "date": "June 21, 2026",
        "summary": "Better support for screen readers on the home, Pulse and People pages.",
        "changes": [
            "Profile photos across the People pages now carry the person's name, so "
            "someone using a screen reader hears who each picture is instead of a blank "
            "image.",
            "The small decorative icons on the home page and in the search box are now "
            "skipped by screen readers, so they no longer interrupt the reading of the "
            "page with meaningless graphics.",
        ],
    },
    {
        "version": "1.37",
        "date": "June 21, 2026",
        "summary": "Clearer “nothing here yet” messages and small readability fixes.",
        "changes": [
            "When a page has no data yet — no people, no activities, no responses — it now "
            "shows a tidy, consistent little message instead of a bare line of text, so it’s "
            "clear nothing is broken.",
            "Nudged one accent colour (amber) slightly darker so every colour scheme now "
            "meets the international readability standard, even on its own tinted background.",
            "Fixed the Name cleanup page so its description text shows in the proper muted "
            "style, and tidied the Sharing settings page title to match the rest.",
        ],
    },
    {
        "version": "1.36",
        "date": "June 21, 2026",
        "summary": "See your own feedback snapshot the moment you log in.",
        "changes": [
            "After signing in, a small card now pops up showing your latest rating, "
            "whether it's trending up or down compared to last quarter, where you stand "
            "among your peers, and — if there’s something worth watching — which area "
            "has the most room to grow. It appears once a day; close it to go straight "
            "to the dashboard, or choose “Don’t show daily” to turn it off.",
        ],
    },
    {
        "version": "1.35",
        "date": "June 21, 2026",
        "summary": "Tidier colours and consistent page titles across the whole dashboard.",
        "changes": [
            "Text colours for status badges (green ticks, amber warnings) and two "
            "accent colour schemes (teal and emerald) have been adjusted so they "
            "meet the international readability standard in every theme — light, "
            "dark, and high-contrast. Nothing moves; things are simply easier to "
            "read at a glance.",
            "Every dashboard page now uses the same layout pattern for its title "
            "and opening description, so the header looks and behaves consistently "
            "wherever you are in the system.",
        ],
    },
    {
        "version": "1.34",
        "date": "June 21, 2026",
        "summary": "Save and share a filtered report view — pin it under a name or copy a link.",
        "changes": [
            "When you've narrowed a dashboard or report — picked a division, a "
            "time period, or a particular view — the scope bar at the top now lets "
            "you keep it. “Copy link” copies a web address that reopens the report "
            "exactly as you've filtered it, so you can paste it into an email or "
            "chat and a colleague sees the same view. “Save view” pins the current "
            "view under a name you choose; “Saved views” then lists them for "
            "one-click return. Saved views are kept on the device you're using.",
        ],
    },
    {
        "version": "1.33",
        "date": "June 21, 2026",
        "summary": "Answer surveys with no internet — answers save on the phone and send themselves once you're back online.",
        "changes": [
            "If you submit a survey while your phone has no signal, your answers are "
            "now saved safely on the device instead of being lost — you'll see a "
            "“Saved on your device” message. The moment the phone is back online "
            "(or the next time the survey is opened), the saved answers are sent "
            "automatically, and a small counter shows how many are still waiting. "
            "This makes it practical to collect feedback at venues with weak or no "
            "internet and sync everything later. If a survey has already closed by "
            "the time a saved answer tries to send, it's flagged clearly rather than "
            "disappearing silently.",
        ],
    },
    {
        "version": "1.32",
        "date": "June 21, 2026",
        "summary": "Add the survey to your phone's home screen — and it still opens if you lose signal.",
        "changes": [
            "Surveys can now be installed like an app: open a survey link on your "
            "phone and choose “Add to Home Screen” to get an icon that opens "
            "straight back to that survey. Once you've opened a survey while "
            "online, it will keep loading even if you lose your connection — handy "
            "for collecting feedback at venues with weak signal. (Sending answers "
            "still needs a connection for now; saving them to send later is coming "
            "next.)",
        ],
    },
    {
        "version": "1.31",
        "date": "June 21, 2026",
        "summary": "Your survey progress is now saved automatically — come back and pick up where you left off.",
        "changes": [
            "If you close the survey tab or step away mid-form, your answers are "
            "saved to your browser. When you reopen the same survey link, a banner "
            "asks whether to resume your draft or start fresh — so no one has to "
            "fill in the same ratings twice. Drafts are kept for 7 days and cleared "
            "automatically once you submit.",
        ],
    },
    {
        "version": "1.30",
        "date": "June 21, 2026",
        "summary": "The monitor page now shows a live response counter that updates the moment someone submits.",
        "changes": [
            "When you open the Monitor page during an active activity, the "
            "Completed CSS number now updates in real time — no refreshing "
            "needed. A green pulse dot next to the count shows the live "
            "connection is active; it turns grey if the connection drops and "
            "reconnects automatically.",
        ],
    },
    {
        "version": "1.29",
        "date": "June 21, 2026",
        "summary": "Search now finds activities and people — not just menu pages.",
        "changes": [
            "The Ctrl-K search palette (and the search box on the home page) now "
            "looks inside your data as well as the navigation. Type an activity "
            "name, topic, organiser, or a staff member's name and the matching "
            "activities and people appear right in the results list — grouped by "
            "type, with a short description beside each one.",
        ],
    },
    {
        "version": "1.28",
        "date": "June 21, 2026",
        "summary": "One-question-at-a-time mode now waits when a follow-up note appears.",
        "changes": [
            "In the focused “one question at a time” survey view, picking a low or "
            "high rating opens a short note box for that question. The form no "
            "longer jumps ahead to the next question while that box is showing — it "
            "waits so you can type your note, then move on with Next when you're ready.",
        ],
    },
    {
        "version": "1.27",
        "date": "June 20, 2026",
        "summary": "Hover over any chart dot to see the exact value — and how it moved.",
        "changes": [
            "Every line chart on the Trends and Participation dashboards now shows a "
            "tooltip when you hover over a data point: the period label, the exact "
            "value, and how much it changed compared to the period before. A small "
            "badge at the end of each line also shows the most recent period-over-"
            "period move at a glance.",
        ],
    },
    {
        "version": "1.26",
        "date": "June 20, 2026",
        "summary": "Answer the survey one question at a time — or all at once.",
        "changes": [
            "A new “Answer one at a time” button at the top of any survey lets you "
            "switch to a focused, one-question view: one question fills the screen, "
            "with Back and Next buttons to move between them. The form auto-advances "
            "after you pick a rating, and you can switch back to the full-scroll view "
            "at any time without losing your answers.",
        ],
    },
    {
        "version": "1.25",
        "date": "June 20, 2026",
        "summary": "The survey now prompts you to explain a low rating — and celebrates a high one.",
        "changes": [
            "When you give a low score on any question, an “Add a note” box "
            "automatically opens with a prompt asking what fell short — so you "
            "can explain without hunting for the comments section.",
            "When you rate the overall quality, the comments section adapts: "
            "a low rating prompts “What could be improved?” and a high rating "
            "asks “What stood out?” so the question always matches how you felt.",
        ],
    },
    {
        "version": "1.24",
        "date": "June 20, 2026",
        "summary": "Mistakes are caught as you type — no more surprises on submit.",
        "changes": [
            "The sign-in and survey forms now tell you about a problem the moment "
            "you leave a field — a red message appears right below it saying what's "
            "wrong (for example “Please enter a valid email address” or “This field "
            "is required”). If you click Submit with anything missing or wrong, every "
            "problem lights up at once and the page scrolls to the first one, so you "
            "can fix things without having to guess what went wrong.",
        ],
    },
    {
        "version": "1.23",
        "date": "June 20, 2026",
        "summary": "Filipino now covers the full respondent journey, not just the survey form.",
        "changes": [
            "The language toggle (EN / FIL) now works on every page a respondent "
            "touches: the activity sign-in and registration form, the RA-10173 "
            "privacy notice, the combined resource-person survey, and the thank-you "
            "page after submitting — including the certificate download buttons and "
            "the back-to-activity link. The activity link tree also shows resource "
            "person and programme labels in Filipino when that language is selected.",
        ],
    },
    {
        "version": "1.22",
        "date": "June 20, 2026",
        "summary": "The survey form can now be answered in Filipino.",
        "changes": [
            "People answering a survey can now switch the whole form between "
            "English and Filipino with the “EN / FIL” buttons at the top of the "
            "page — the questions, the rating choices, and every label change "
            "language together, and the system remembers the choice for next time. "
            "The Filipino wording is a first version for the office to review and "
            "refine over time.",
        ],
    },
    {
        "version": "1.21",
        "date": "June 19, 2026",
        "summary": "Admins can now close all historical activities to paper encoding.",
        "changes": [
            "The Paper entry page now has a “Close all to encoding” button for admins. "
            "Clicking it hides all existing activities from the encode picker so encoders "
            "can no longer key in new paper slips for them — but nothing is deleted: "
            "every response still appears in all reports and dashboards as before.",
        ],
    },
    {
        "version": "1.20",
        "date": "June 19, 2026",
        "summary": "Better text colours across every page in dark mode.",
        "changes": [
            "Every page now uses text colours that adapt to the theme you have "
            "chosen. Warning banners, status flags, chart labels, action buttons, "
            "and category badges all flip to a readable shade in dark mode instead "
            "of showing dark text on a dark background.",
        ],
    },
    {
        "version": "1.19",
        "date": "June 19, 2026",
        "summary": "Filter written comments by scope and period — and better dark-mode colours.",
        "changes": [
            "The Written Comments page now has the same Scope and Period selectors "
            "as the other reports — so you can narrow the comments to a specific "
            "division, section, or time period without going back to the reports hub.",
            "Fixed a dark-mode display issue on activity scorecards where the big "
            "numbers and some verdict labels were hard to see against the card "
            "background — they now use the right colours in every theme.",
        ],
    },
    {
        "version": "1.18",
        "date": "June 18, 2026",
        "summary": "A lighter, faster system behind the scenes.",
        "changes": [
            "The dashboards and reports now run on a fraction of the memory they "
            "used to, and the figures behind them are prepared noticeably faster — "
            "so pages stay quick and the system keeps more headroom as the records "
            "keep growing. Nothing changes in what you see; it just runs leaner.",
        ],
    },
    {
        "version": "1.17",
        "date": "June 18, 2026",
        "summary": "Smoother comment sorting and a one-click “save both” when editing activities.",
        "changes": [
            "On the written-comments page, re-sorting a comment (Appreciated, Mixed "
            "or To improve) no longer reloads the whole page — the comment updates "
            "right where it is and shows a “✓ re-tagged” mark, so you can see at a "
            "glance what you've already done and never lose your place.",
            "When editing activities, you can now type a new name AND pick a new "
            "section, then click “Apply all changes” once to save both together — no "
            "more saving the rename, reopening, and re-filing separately. A single "
            "undo reverses both.",
        ],
    },
    {
        "version": "1.16",
        "date": "June 18, 2026",
        "summary": "Your data is now saved permanently and survives every system update.",
        "changes": [
            "The system now keeps your information on permanent storage, so nothing "
            "is lost when the app updates or restarts — edits like renaming and "
            "merging activities are saved continuously and brought back automatically.",
        ],
    },
    {
        "version": "1.15",
        "date": "June 18, 2026",
        "summary": "Jump straight to a page in the activities list — and search it more easily.",
        "changes": [
            "The activities list can run to hundreds of pages, so the bottom of the "
            "list now has a “Jump to” box: type a page number, press Go, and you're "
            "there — no more clicking “Older” one page at a time.",
            "A search box now also sits at the foot of the list, with a reminder that "
            "searching by activity or organiser name is the quickest way to find what "
            "you're after.",
        ],
    },
    {
        "version": "1.14",
        "date": "June 18, 2026",
        "summary": "Editing activities keeps your place in the list.",
        "changes": [
            "When you rename, merge, re-file or archive activities from the "
            "“Edit & merge activities” list, you now stay on the same page you "
            "were working on — with the same sort and search — instead of being "
            "sent back to the top of the first page each time.",
        ],
    },
    {
        "version": "1.13",
        "date": "June 18, 2026",
        "summary": "A faster home page, especially right after the app wakes up.",
        "changes": [
            "The home page now loads its summary numbers and activity lists "
            "noticeably faster — most noticeable the first time you open it after "
            "the system has been idle. Behind the scenes the app no longer re-reads "
            "every past response just to show this week's totals.",
        ],
    },
    {
        "version": "1.12",
        "date": "June 18, 2026",
        "summary": "Cleaner one-activity downloads — a proper scorecard instead of an empty timeline.",
        "changes": [
            "When you download a resource person's report for a single activity, it no "
            "longer shows a “scores over time” chart with just one dot — which never "
            "made sense for a one-off session. Instead it leads with a clear scorecard: "
            "the score, the rating band, how many people rated, and how it compares to "
            "the bureau average.",
            "Fixed the comparison on those single-activity downloads: it now measures "
            "against the real bureau average instead of comparing the session to itself "
            "(which always read as “right around average”).",
        ],
    },
    {
        "version": "1.11",
        "date": "June 18, 2026",
        "summary": "See how a resource person did at one specific activity — with its own page and downloads.",
        "changes": [
            "On a person's page you'll now find a “Per-activity engagements” list — "
            "every activity they spoke at since June 15, 2026, marked as either an "
            "invited (outside) activity or a bureau-led one.",
            "Tap any activity to open its own scorecard for that person: their rating "
            "for that session, what stood out, the comments people left, and a short "
            "coaching note — separate from their overall all-time report.",
            "Each of those per-activity scorecards can be downloaded on its own as a "
            "PDF, PowerPoint, Excel sheet, or image.",
        ],
    },
    {
        "version": "1.10",
        "date": "June 17, 2026",
        "summary": "The home “Recent activities” list now focuses on the last 7 days.",
        "changes": [
            "The “Recent activities” list on the home page now shows only "
            "activities from the last 7 days (and any still to come), so it stays "
            "even shorter and more current — just this week's work at a glance.",
        ],
    },
    {
        "version": "1.9",
        "date": "June 17, 2026",
        "summary": "The home “Recent activities” list now focuses on the last 30 days.",
        "changes": [
            "The “Recent activities” list on the home page now shows only "
            "activities from the last 30 days (and any still to come), so it stays "
            "short and current instead of filling up with older items.",
        ],
    },
    {
        "version": "1.8",
        "date": "June 17, 2026",
        "summary": "Admins can now archive any activity right from the home page.",
        "changes": [
            "If you're an admin, “Your recent activities” on the home page now shows "
            "every recent activity across the office — not just the ones you set up — "
            "so you can Archive any standalone activity in one tap.",
            "The “Archived activities” page now lists everything that's been put away, "
            "including older items that weren't tied to a person, so an admin can "
            "restore any of them.",
        ],
    },
    {
        "version": "1.7",
        "date": "June 17, 2026",
        "summary": "Archive a standalone activity instead of deleting it — and restore it any time.",
        "changes": [
            "If you created an activity that should no longer count — for example a "
            "speaker rating you set up by mistake or one that ended with no responses "
            "— you can now Archive it straight from “Your recent activities” on the "
            "home page. It disappears from every list, feed and total at once.",
            "Nothing is deleted: a new “Archived activities” page lists everything "
            "you've put away, and one tap restores any of them, fully intact.",
        ],
    },
    {
        "version": "1.6",
        "date": "June 17, 2026",
        "summary": "Easier list editing, clearer speaker sections, and your own friendly activity links.",
        "changes": [
            "When you're tidying up the activities list, the “Edit / merge”, "
            "“Expand all” and “Collapse all” buttons now stay on screen as you "
            "scroll, so you no longer have to scroll back to the top to use them.",
            "On the single combined survey, each speaker now stands out clearly — "
            "with a coloured stripe down the side and a “Speaker 1 of 3” label — so "
            "it's obvious where one section ends and the next begins.",
            "You can now give an activity a short, friendly web link of your own "
            "(for example “…/e/les-quezon-june”) instead of the long random one, "
            "making it easier to share — and the original link and any QR codes "
            "you've already printed keep working.",
        ],
    },
    {
        "version": "1.5",
        "date": "June 17, 2026",
        "summary": "Clearer survey wording, easier speaker ratings, and a fuller home page.",
        "changes": [
            "The combined survey for invited activities now gently guides you with "
            "ready-made prompts again, so it's easier to know what to write.",
            "The box that used to say “Honorific” now simply says “Title”, so it's "
            "clear what to put there.",
            "The home page now also shows activities that are still collecting "
            "speaker ratings even when there's no formal event attached, so nothing "
            "in progress gets missed.",
        ],
    },
    {
        "version": "1.4",
        "date": "June 17, 2026",
        "summary": "Manage the activities you were invited to, and clearer feedback comments.",
        "changes": [
            "Activities run by an outside group — where your staff took part only as "
            "resource persons — now keep their name and have their own page where you "
            "can re-print the QR codes, change when feedback is open, add or rename "
            "speakers, and close or archive the activity once it's done.",
            "For those invited activities, the single combined QR code now opens ONE "
            "page where a person can rate every speaker and submit just once — and "
            "they can tick “I didn't attend this one” to skip any session they missed.",
            "You can now follow responses to invited activities from the Monitor — how "
            "many answers came in, when, and the overall mix of who replied — kept "
            "fully anonymous, with no names shown.",
            "The written-comments report is easier to read: it tells the story in "
            "words instead of long tallies, and a comment that is both praise and a "
            "suggestion (“great session, but the room was cold”) now correctly appears "
            "under both “what people appreciated” and “what to improve”.",
        ],
    },
    {
        "version": "1.3",
        "date": "June 17, 2026",
        "summary": "Frame profile photos just the way you want them.",
        "changes": [
            "When you add or change a staff member's profile photo, you can now "
            "zoom in and drag the picture to frame it nicely inside the round "
            "avatar — no more faces getting cut off or sitting off-centre.",
        ],
    },
    {
        "version": "1.2",
        "date": "June 17, 2026",
        "summary": "Tidier feedback and activity tools, plus speakers shown on activity cards.",
        "changes": [
            "Once your Spot Feedback is finished, you can now tuck it into an "
            "“Archived” section to keep your feedback list clean — and bring it "
            "back any time.",
            "Fixing or merging activity names is easier to find under a new "
            "“Edit & merge activities” menu item, and a friendly green message "
            "now confirms when a change goes through.",
            "Activity cards on the home page now show who the speakers or "
            "resource persons are.",
        ],
    },
    {
        "version": "1.1",
        "date": "June 17, 2026",
        "summary": "Version tracking starts here, plus recent quality-of-life upgrades.",
        "changes": [
            "The sign-in screen now shows a version number so everyone knows "
            "which build of the system they are using.",
            "Times and dates now show in Philippine time, so the activity log "
            "matches your watch instead of running hours behind.",
            "When you send Spot Feedback you now get a friendly “we heard you” "
            "reply, can follow its status, and see a bell notification when "
            "there is an update for you.",
            "You can now personalise the look — pick an accent colour, light or "
            "dark mode, and text size — and the Equity in Health logo now "
            "appears across the system.",
            "The home page now shows a quick strip of your recent activities.",
        ],
    },
]

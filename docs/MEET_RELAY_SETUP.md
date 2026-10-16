# Google Meet relay setup

When someone saves a calendar item whose modality is **Online** or **Hybrid** and the meeting link is empty, the Space asks a small Google Apps Script to make a Google Calendar event with a Meet link and puts that link in the item's meeting link. Editing the item moves the event; cancelling it deletes the event. A link the person typed themselves (Zoom, Teams, their own Meet) is never touched.

If the relay is not set up, or Google is slow or down, the item still saves; the banner says no link was made and the person can paste one.

## What a person has to do

1. **Create the script.** Sign in as the shared organizer mailbox, `blhsd@doh.gov.ph`. Every Meet link belongs to this account. Open <https://script.google.com>, New project, paste in `apps_script/meet_relay.gs`.
2. **Enable the Calendar service.** Services (the + beside it), Google Calendar API, v3, Add.
3. **Script Properties** (Project settings): `SHARED_SECRET` (a long random string). Optional: `CALENDAR_ID` (default `primary`), `TIME_ZONE` (default `Asia/Manila`) and `ALLOWED_DOMAIN` (default `doh.gov.ph`).
4. **Deploy.** Deploy, New deployment, Web app. Execute as: **Me**. Who has access: **Anyone**. Authorise the Calendar scope. Copy the `/exec` URL. Every later change needs Deploy, Manage deployments, New version.
5. **Set the Space secrets:** `CSS_MEET_RELAY_URL` (the `/exec` URL) and `CSS_MEET_RELAY_SECRET` (the same string as `SHARED_SECRET`). Restart the Space.
6. **Test.** Add a calendar item with modality Online and no link. The saved page should show a `meet.google.com` link, and the event should appear in the organizer's Google Calendar.

## How it behaves

- The endpoint is open, so nothing is trusted without a signature: HMAC-SHA256 over `timestamp.payload`, rejected if wrong or more than 5 minutes off (same scheme as the travel documents relay).
- The calendar item's `uid` is stored on the event, so a retry never makes a second link, and edits and cancels find the event without the app storing an event id.
- The people on the item are added to the Google event as guests, only if their address ends in `ALLOWED_DOMAIN` (default `doh.gov.ph`), and no Google invitation email goes out (`sendUpdates: none`). People are told by the app's own calendar emails. The event then shows on their own Google Calendar with a **Join with Google Meet** button, and they join without knocking.
- Guests are not made Meet **co-hosts**: Google's Calendar API can't do that. The organizer, or a Meet host who opens the event's *Video call options* in Google Calendar, can assign co-hosts by hand (needs a Workspace edition that supports co-hosts).
- Meet admission follows the organizer account: people in the `doh.gov.ph` Workspace join directly; people outside it usually have to be admitted by someone in the meeting.
- Items with no start time become all-day events. The link still works.
- A failed or slow relay call (25 second limit) never blocks a save.

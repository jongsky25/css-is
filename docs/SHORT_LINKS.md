# Public short links (Short.io)

## Configure the Hugging Face Space

In Settings → Variables and secrets:

| Type | Name | Value |
|---|---|---|
| Secret | `SHORT_IO_API_KEY` | Private Short.io API key authorized for the chosen domain |
| Variable | `SHORT_IO_DOMAIN` | `blhsd.s.gy` (also the application's default) |
| Variable | `CSS_SHORT_LINKS` | `1` to enable; defaults to `0` |
| Variable | `CSS_BASE_URL` | `https://equityinhealth-office-connect.hf.space` |

Restart after changing settings. No key is included in source, browser responses or
logs. A missing key leaves jobs queued without consuming attempts. Authentication or
quota errors pause requests for an hour and are shown on sharing pages. Fix the
account/key, then restart or allow the scheduled retry to run.

The selected domain must belong to the Short.io account associated with the key.
The runtime has no way to verify this until an authenticated API call succeeds.

## Migration and verification

Deploying this version migrates unsuccessful is.gd jobs to pending Short.io jobs,
clearing their previous failure/cooldown. Completed mappings stay intact, including
any successful is.gd links. No old short URL is deleted, repointed or recycled.

Open one existing activity's sharing page. When its job is processed, its URL should
be `https://blhsd.s.gy/...`. Confirm that it opens the intended registration page,
then download/scan the matching QR. Also verify an individual feedback form.
Short.io calls require the Space secret; mocked tests do not establish live account access.

For older active activities not already queued, run `python short_links.py --backfill`
in the deployed environment with the same settings/database as the app. This is
resumable and excludes archived activities/forms. It includes standalone public forms.
Do not run bulk backfill before validating the account and considering the free plan's
1,000 lifetime link-creation allowance.

## Behavior

- Create new links through `POST https://api.short.io/links`, using `Authorization`
  and JSON fields `domain`, `originalURL`, and `allowDuplicates: false`. No custom
  path is sent. Short.io documents returning an existing mapping for the same
  original URL when no path is supplied; repeated retries need not create duplicates.
- Public `/e/<token>`, `/r/<token>` and `/seq?tokens=...` only. Activity destinations
  use stable tokens so editing their readable slug does not invalidate a short link.
- Signed participant recovery/certificate URLs are excluded. The provider receives
  the full public destination and handles visitors' redirects.
- SQLite stores mappings and retry state. Page rendering does not call the provider;
  a background worker claims a lease and releases the DB lock before network access.
- Conservative shared pacing: one request per 25 seconds per database, 60-second
  leases, 8-second HTTP timeout and no redirect following. Unexpected responses,
  transport errors and server failures retry with exponential backoff up to a day.
- HTTP 429 pauses all jobs for at least 60 seconds, honoring numeric Retry-After
  up to one day. HTTP 401/403 and 402 pause all jobs for an hour. HTTP 400/404/409/422
  marks the affected job failed. Failed jobs are not automatically resubmitted.
- Only valid HTTPS short URLs on the configured domain are accepted. Ready legacy
  mappings remain reusable after changing providers/domains.
- Sharing controls show status/retry timing and poll for ten visible minutes,
  updating the link, QR image and download together. Original links remain available.
  Reopening the page picks up later results.
- `CSS_NO_SCHEDULER=1` disables the worker; keep it unset in production.
- Set `CSS_SHORT_LINKS=0` to stop new provider requests and show original links.
  Existing mappings remain in the database/backups. Distributed short links still
  depend on the provider being available.
- Closing an activity does not repoint its short link. Historical posters and messages
  must continue to identify their original activity.
- Combined feedback links represent their exact token list. If speakers change,
  reprint the combined QR sheet for the new list.

Read-only inspection:

```sql
SELECT provider,status,COUNT(*) FROM short_links GROUP BY provider,status;
```

## Why is.gd was replaced

On October 16, 2026, direct tests returned HTTP 200 with `Error, database insert failed`
for the app's URL and a new Wikipedia URL variant. A common Wikipedia URL returned
an existing short URL. This was consistent with a new-mapping failure outside the app.
The user confirmed their original registration link opens; an unauthenticated 404
observed during investigation did not establish that the activity was missing.

API reference: https://developers.short.io/reference/post_links

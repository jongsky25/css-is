# Public short links (is.gd)

The integration is opt-in. It requires no provider account or API key.

## Configuration and rollout

1. Keep `CSS_SHORT_LINKS=0` (the default) while deploying and reviewing.
2. Set `CSS_BASE_URL` to the permanent, publicly reachable HTTPS origin, without a path.
   Changing this later cannot retarget existing is.gd links. Keep the old origin serving
   redirects if the application moves. Localhost, private IPs and local/test origins are excluded.
3. Set `CSS_SHORT_LINKS=1`, restart the app, and create one test activity. Verify its
   registration and feedback destinations and download/scan a QR. No secrets are needed.
4. For existing active activities, run `python short_links.py --backfill` in the deployed
   environment with the same `CSS_DB`, `CSS_BASE_URL` and `CSS_SHORT_LINKS` as the app.
   This only queues links, is safe to repeat, and excludes archived forms/activities.
   It also includes active standalone feedback forms. The running app drains the queue.
5. To stop new shortening and return sharing controls to original URLs, set
   `CSS_SHORT_LINKS=0` and restart. Retain the mapping table for later reuse.

`CSS_NO_SCHEDULER=1` also disables the worker, for tests and CLI usage. Do not set it
on the production app if you expect queued links to be processed.

## Behavior

- Public `/e/<token>`, `/r/<token>` and `/seq?tokens=...` destinations only. Activity
  destinations use the original token, so edits to the readable custom slug are safe.
- The `short_links` table stores the exact original URL, provider, short URL, status,
  timestamps, attempts, last error category and next attempt. Existing normal SQLite
  snapshots include this table and the `short_link_rate` pacing row.
- Creation enqueues public links in the same transaction as the form/event. Opening a
  sharing page also queues any missing mapping. Page rendering never calls is.gd.
- Sharing controls initially show the original link, then poll for up to ten visible
  minutes to replace the URL, QR image and download with the saved short link. A later
  page load picks up completed mappings. The original link remains available.
- Requests are HTTPS form-encoded POSTs to `https://is.gd/create.php`, with JSON output,
  no optional statistics, no redirect following, and an 8-second httpx timeout.
- Workers sharing a database reserve one request slot every 25 seconds (at most 144/hour)
  and a 60-second job lease under a short write transaction; no DB lock spans HTTP.
  is.gd limits are per outbound IP: other apps on the same IP also consume that allowance.
- Errors retry with exponential delay up to a day. Provider rate-limit error 3 pauses
  all shortening for at least an hour. Invalid destination/alias errors stop that job.
  Transport and malformed-response failures leave the original URL usable. Worker
  crashes recover after the lease expires; normal shutdown finishes an in-flight call.
- The worker rechecks destination eligibility before sending (including the current
  canonical origin). Status polling is authenticated and cannot enqueue arbitrary URLs.
- Recovery, certificate and participant-signed links are excluded. is.gd receives the
  complete public destination URL and handles visitors' redirects.
- Old printed QR codes remain valid. A provider outage can still affect short links
  already distributed; the original-link fallback only helps newly displayed/shared links.
- Combined speaker URLs are snapshots of their token list. Adding/removing speakers
  generates a new destination and short link; reprint the combined QR sheet as before.

## Inspection

Read-only queue summary:

```sql
SELECT status, COUNT(*) FROM short_links GROUP BY status;
SELECT COUNT(*), MAX(updated_at) FROM short_links WHERE status='ready';
```

The public endpoint is not configurable. A provider change should be a deliberate code
change with its own validation, rather than sending destinations to arbitrary hosts.

References: https://is.gd/apishorteningreference.php and https://is.gd/usagelimits.php.

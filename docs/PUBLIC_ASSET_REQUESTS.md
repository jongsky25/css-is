# Public asset requests

Introduced in **7.69**, the second A13 performance increment.

## Request boundary

GET and HEAD requests to `/static/`, `/sw.js`, `/manifest.webmanifest` and
`/favicon.ico` proceed to their existing route without resolving a session,
permissions or navigation notifications. The static mount serves packaged
public files only. Neither file extensions nor query parameters identify an
asset. Path comparison uses Starlette's router-relative path, including when
the application has a `root_path` such as `/office` or `/static`.

Other public routes retain their normal processing, including database-backed
directory photos, survey pages and machine callbacks. Private photos,
signatures, document pages and exports still use current session and permission
checks. Unsafe methods on asset paths still pass through the origin check.

## Behavior preserved

- Static file bytes, missing-file and traversal denials, ETags, Last-Modified,
  conditional 304 responses and byte ranges are handled by the same static mount.
- The service worker still revalidates with `no-cache`; the manifest remains
  `no-store` because its start URL can contain a participant token.
- Browser security headers and the `X-CSS-App` response marker still apply.
- Request status, timing and traffic metrics still run. Asset request logs have
  no resolved account name, even if the browser sent a session cookie.
- Existing route methods/statuses are preserved: root service-worker and manifest
  GET routes do not implement HEAD; the root favicon path currently returns 404.

## Local evidence

`tests/test_public_asset_requests.py` runs complete HTTP requests against the
synthetic reference database and instruments `sqlite3.connect` and SQLite's
statement trace. It covers seven paths with GET and HEAD (14 requests), including
missing files and the root routes listed above.

| Session | Before: connections / SQL statements | After: connections / SQL statements |
|---|---:|---:|
| Active viewer | 28 / 490 | 0 / 0 |
| Anonymous, revoked or malformed | Not measured as a before/after comparison | 0 / 0 each |

The before measurement was reproduced on the 7.68 implementation, with the
same test client, synthetic fixture and warm schema. Counts include connection
PRAGMAs, session validation and middleware reads. They are not latency or
production capacity measurements. A separate test makes SQLite unavailable
and checks that CSS bytes, the service worker and manifest still load.

The 43 regression cases also exercise cache validation and ranges, security
headers, metrics, unsafe methods, private routes and similar path names,
session revocation after an asset read, traversal, database-backed public images
and application mount prefixes.

## Rollout and remaining work

There are no new dependencies or schema/data changes. Current login sessions
and document permissions are unchanged. No manual production testing was used.
This increment eliminates database work for public asset reads; it does not
change page-query performance. Other Home and request permission duplication
remains a separate A13 increment.

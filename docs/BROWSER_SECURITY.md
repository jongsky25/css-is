# Browser security — A06, browser defaults only

## Scope

This increment covers HTTPS cookies, browser security headers and private
response caching. First-admin setup, login/reset throttling and password/hash
changes are excluded from the current enhancement at the owner's direction.
No account, password, session-token format or database migration is introduced.

## Cookies and transport

- `SPACE_HOST` or an HTTPS `CSS_BASE_URL` enables Secure cookies automatically,
  including behind the hosting provider's TLS terminator. An explicit
  `CSS_SECURE_COOKIES=0` cannot disable this production protection.
- `CSS_SECURE_COOKIES=1` remains available for other deployments. With no HTTPS
  configuration, local HTTP/LAN development continues to work.
- The response boundary also adds Secure to every cookie on a trusted ASGI
  HTTPS request, including recognition, calendar preference and deletion
  cookies. Existing HttpOnly, SameSite, path and expiry attributes are retained.
- Raw `X-Forwarded-Proto` and `X-Forwarded-Host` headers do not decide this policy.
  Configure the canonical origin and only trust actual reverse proxies in
  Uvicorn. This change does not broaden proxy trust or introduce HTTP redirects.
- HTTPS requests/configured HTTPS deployments emit HSTS with a one-day max age.
  There is no includeSubDomains or preload commitment. Validate the public edge
  before increasing that duration. Browsers ignore HSTS received over HTTP.

## Headers and script rollout

Every response, including authentication denials, redirects, validation errors
and the application's unhandled 500 response, receives:

- `X-Content-Type-Options: nosniff`.
- `Referrer-Policy: same-origin`, keeping bearer paths and query strings out of
  every referrer sent to another site. It is deliberately not `no-referrer`: with that policy Chrome and Edge
  send a form POST with `Origin: null` and no Referer, and the origin check on writes then rejects every login and
  save. `same-origin` lets the site's own requests carry their real Origin.
- `X-Frame-Options: SAMEORIGIN` and an enforced CSP with
  `frame-ancestors 'self'; base-uri 'self'; object-src 'none'`.

Another origin cannot embed the application. Open the direct `.hf.space` URL;
embedding it in the Hugging Face website's outer frame is intentionally blocked.
Same-origin email previews remain allowed. `frame-ancestors` does not restrict
the app's outgoing Google Drive preview frames. No global frame-src or
default-src restriction is enforced in this increment.

The broader resource/script policy is **report-only**, to preserve existing
inline scripts while establishing a migration target. It allows same-origin
scripts/resources and Google Drive frames, with image/style/worker allowances
for current UI patterns. Browser-console violations do not block scripts.
It is not a completed inline-script/XSS defense. There is no report receiver,
report-sample directive or external report destination that might collect
private document/participant URLs or script contents. Before enforcement,
inventory console violations, migrate inline scripts/handlers to nonces or
external files and verify each affected workflow, including PDF workers.

## HTTP caching and the service worker

- Dynamic responses, including login/account pages, participant/bearer pages,
  exports, JSON, manifests containing launch URLs, photos and errors, use
  `no-store` with legacy no-cache headers and `Vary: Cookie, Authorization`.
  Existing private/no-store policies are retained. Streaming/download bodies,
  content types and attachment headers are untouched.
- Successful public `/static/` assets remain cacheable and retain validators.
  Failed asset responses and responses setting cookies cannot inherit that
  exception. `/sw.js` revalidates with `no-cache`.
- Cache Storage is manual and does not obey HTTP cache policy automatically.
  The worker now caches only public static assets, rejects private/no-store or
  redirected asset responses, and removes rejected runtime entries. Participant
  pages and photos are never written or read from its dynamic caches.
- Offline navigation uses only the generic static offline shell. Previously
  visited participant pages and personal photos are no longer available offline.
  Already-open forms and the existing deduplicated survey submission queue keep
  their current behavior; this change does not delete queued answers or add a
  new offline queue.
- The release's worker cache version purges previous Office Connect caches on
  activation. Older installed clients retain their previous worker behavior
  until the new worker installs/activates. HTTP no-store cannot retroactively
  erase all browser history or content already stored by older software.

## Verification and rollout

Focused HTTP tests cover configuration, HTTPS login/logout, multiple cookies,
framing/resource headers, early denials, validation/500 errors, private pages,
assets/304 responses and streaming attachments. Node executes the real service
worker against personal navigation/photo cache attempts, private asset replies,
offline fallbacks, lifecycle cleanup and ambiguous write failures. Chromium
checks foreign-frame rejection and same-origin preview/inline-script behavior;
the full existing browser suite checks the app's interactive workflows.

GitHub's required normal and shuffled Python 3.11 suites must pass before
promotion. Manual production workflow testing remains deferred. After a later
authorized deployment, verify actual HTTPS response/cookie headers through the
public edge, login/logout, email/Google Drive previews, PDF page processing and
worker adoption. Do not claim edge configuration or installed-client adoption
from local test results. Roll back with a new worker cache generation and a
forward release; an older worker can restore the previous private-cache risk.

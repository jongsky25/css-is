# Optional Telegram outbound service

This is a conditional transport for Office Connect's central `@blhsd_bot` worker when its main host cannot reach Telegram. The live v9.52 probe reported Requests read timeout and HTTPX connect timeout before any HTTP response. Activation remains pending exact service verification and workspace identification. No service has been created by this change, and the transport defaults to the existing direct path while `CSS_TELEGRAM_OUTBOUND_URL` is absent.

## Authority and data

Office Connect keeps the database, permissions, consent, queue, business actions and receipts. The isolated service accepts only signed requests from `https://equityinhealth-office-connect.hf.space` for `getMe`, `getChatMember` and `sendMessage`. It cannot choose another upstream URL or use other Bot API methods.

The existing bot token travels with the signed request over verified HTTPS to the owned service and then Telegram. The service uses it only in request memory and never logs or stores it. Staff passwords, application admin credentials and the Telegram webhook secret are never supplied to this service. Existing per-account Apprise targets retain their separate transport.

An Ed25519 key is derived with a domain separator from the bot's existing high-entropy credential. `/integrations/telegram/outbound-key` exposes only its public verification key when the optional transport is configured. The service fetches it from the fixed source origin with TLS verification and no redirects. Requests bind their method, parameters, nonce and 20-second expiry. Unsupported, malformed, expired or tampered requests are refused before provider I/O.

For a message send, the nonce is the primary database's existing delivery claim token. Before calling Telegram, the service submits the signed request to `/integrations/telegram/outbound-permit`. Office Connect rechecks the delivery switch, bot configuration, current eligibility, destination, lease and expiry inside a transaction. It consumes the one-time permit using the existing `error_code='outbound_started'` marker. Only one concurrent request can obtain it. A duplicate request, a new service process or overlapping deploy cannot obtain another permit. The normal finalizer replaces the temporary marker with the provider outcome. No schema migration is required.

No database writer lock is held during HTTP. A sleeping service is warmed through its public health endpoint before Office Connect claims an actual send. The queue remains unattempted while it starts; expired or ineligible deliveries are still cancelled. Provider uncertainty is never automatically retried. Only the existing validated Telegram rate-limit response permits the existing bounded retry path.

## Packaging

- Git repository: `jongsky25/css-is`; the service uses `Dockerfile.telegram-outbound` with its own minimal build context.
- Hashed dependencies are constrained to exact application-audited versions, including packaging tools. CI builds and audits this actual image separately.
- One instance and one Uvicorn process; bind `0.0.0.0:$PORT` (default 10000). No local database, persistent disk or new hosting secrets are required.
- `/health` reports process readiness, protocol, fixed source and the Render source commit. `/connection` performs a cached, credential-free Telegram HTTPS reachability check. Neither sends a message.
- The free web-service plan is suitable for the controlled pilot. It sleeps after inactivity, so the first reply can wait for startup and the next worker tick. Render's [free-instance limits](https://render.com/docs/free) apply, including workspace-shared hours. Continuous production availability requires a separate capacity decision.

## Activation sequence

1. Read the live v9.52 probe and establish that a separate outbound service is needed. Keep the normal host proxy and TLS verification intact.
2. Confirm the target Render workspace. Prepare and pass all required checks on the exact service/application source; keep the candidate disabled until the evidence supports activation.
3. Push a stable `deploy/telegram-outbound` branch to that checked commit. Create the owned service with auto-deploy off, the free web-service plan and the Dockerfile above, using the confirmed workspace. Start and monitor its first deployment; record the service ID, URL, source commit and terminal `live` result. Do not trigger a second deployment while the first is active.
4. Verify the public health/source metadata and credential-free reachability check. Keep all tokens out of tool output and evidence.
5. Merge the checked application PR with this explicit final trailer block, using the owned service's actual public URL and verified service commit:

   ```text
   Telegram-Outbound-URL: https://OWNED-SERVICE.onrender.com
   Telegram-Outbound-Commit: VERIFIED_40_CHARACTER_SERVICE_COMMIT
   ```

   The canonical main deployment alone reads these public trailers. It verifies service protocol, fixed source, exact service commit and Telegram reachability, then secures the existing fresh verified database backup. Only afterward can it set the single public hosting variable `CSS_TELEGRAM_OUTBOUND_URL`. Because that update can restart the old application, it secures another fresh verified snapshot before the code-upload restart. If the old app is still starting, setup aborts safely and can be retried while the old source version remains live; the already-saved URL is idempotent. Backup override flags are refused for this setup. Unrelated releases without the trailer block do not change hosting configuration.

6. Follow the canonical deployment through RUNNING and the matching login version. Its read-only diagnostic job probes at the first and last sample, allowing a sleeping service to start. Verify `network.outbound` returns authenticated HTTP 200 and `bot_username_matches=true`. The expected bot username is compared in the service; only a boolean leaves it.
7. Ask the operator for one genuinely fresh private `/start`. Inspect its actual send outcome and confirm the operator received the reply. Do not replay older uncertain deliveries or mark the complete T4.4 workflow verified from this private-command check.

## Rollback and maintenance

Removing `CSS_TELEGRAM_OUTBOUND_URL` from the hosting settings selects the original direct transport. Secure the same fresh live backup before a hosting change that restarts the application. Keep all uncertain deliveries untouched. The service can remain idle while diagnosis continues; no automatic paid upgrade or additional resource is part of this change.

The Render service is pinned to a stable deployment branch with auto-deploy off. Future service updates must pass the same checks before moving that branch and deploying its exact commit. Record and verify the resulting live service commit separately from the application release. Read-only metadata is not proof that a user received a message.

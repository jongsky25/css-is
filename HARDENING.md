# Pre-production hardening checklist

**October 19, 2026 update:** the deployed configuration still needs verification. Follow [Phase 0 repairs and rollout](docs/PHASE0_REPAIRS.md) for release 7.23, its session migration and recovery checks. Historical deployment assumptions below are not evidence of current settings.

Steps to take the CSS-IS system from "internal LAN pilot" to a production-ready
deployment on the Hugging Face Space `equityinhealth/office-connect`.

Two kinds of work:

- **Dashboard / env actions** (this file) — things only the Space owner can do in
  the Hugging Face web UI or a token dashboard. Claude cannot do these for you.
- **Code changes** — tracked separately in the repo (see the commit history;
  the `CSS_SECURE_COOKIES` cookie hardening is done).

---

## 1. Rotate the exposed Hugging Face token  ⚠️ do this first

A **write** token was pasted in plain chat during earlier setup, so it must be
treated as compromised — anyone holding it can overwrite the live Space.

1. Go to <https://huggingface.co/settings/tokens>.
2. **Revoke** the old token (the `hf_EnDz…` write token).
3. **Create** a new token — scope **Write** (needed for `upload_folder` deploys),
   restricted to this Space if fine-grained tokens are available.
4. Re-cache it locally so deploys keep working:
   ```
   hf auth login --token <NEW_TOKEN>
   ```
   (`hf.exe` lives at
   `C:\Users\USER\AppData\Local\Python\pythoncore-3.14-64\Scripts\hf.exe`.)
5. Never paste the new token into chat or commit it. The cached copy lives at
   `~/.cache/huggingface/token`.

---

## 2. Set the Space secrets & variables

Space → **Settings → Variables and secrets**. Without these, two things break:
logins drop on every rebuild, and HTTPS cookie protection can't turn on.

| Name | Type | Value | Why |
|---|---|---|---|
| `CSS_SESSION_SECRET` | **secret** | a long random string (e.g. `python -c "import secrets;print(secrets.token_urlsafe(48))"`) | `auth.py` signs session tokens with this. If unset, a *new random* secret is generated on every rebuild → **everyone is logged out on each deploy**. |
| `CSS_BASE_URL` | variable | `https://equityinhealth-office-connect.hf.space` | Pins the public origin for QR codes and share/email links (no trailing slash). |
| `CSS_SECURE_COOKIES` | variable | `1` | Marks session + participant cookies `Secure` so they never ride plain HTTP. Code support shipped; this flag turns it on. |

> Verify `CSS_DB`, `CSS_PERSIST_DIR`, the actual mount and snapshot destination — see [DEPLOY.md](DEPLOY.md). Do not disable or reconfigure persistence based on historical DB-in-repository assumptions.

Confirm uvicorn runs with `--proxy-headers` (in the Dockerfile / start command)
so `request.base_url` and the Secure cookies see the real HTTPS scheme behind
HF's proxy.

After setting these, verify the HTTPS cookie attributes and sign-in behavior. Release 7.23 and database restores intentionally require a new sign-in, even with a stable signing secret; remaining signed in is no longer a valid standalone persistence check.

---

## 3. Revert pilot auth → emailed invite links  (deploy the mail relay)

**Done — code side:** account creation and admin "Reset password" now email an
invite/reset link (`_provision_account`, `/admin/users/{id}/reset-default` in
[app.py](app.py)) instead of handing out `auth.DEFAULT_PASSWORD = "12345678"`.
Self-service `/forgot` now has a real form and sends a reset link too. Until a
mail transport is configured, `mailer.send()` can't deliver — the link is shown
to the admin on the Users page instead (never silently lost).

> ⚠️ **SMTP cannot work on this Space.** Its network blocks outbound SMTP on
> every port — `smtp.gmail.com:587` and `:465` both hang until the client
> timeout, while outbound HTTPS is fine (it's how `ai_core.py` reaches Gemini).
> This is not provider-specific: Gmail, Brevo and anything else will fail the
> same way. Do not spend time on `CSS_SMTP_*` here; they're kept in `mailer.py`
> only for networks that do allow SMTP, like the original LAN pilot.

**Still needed — your side:** deploy the HTTPS mail relay and set
`CSS_MAIL_RELAY_URL` + `CSS_MAIL_RELAY_SECRET` on the Space. Full steps
(~5 minutes, no DNS records, no Google Cloud project) are in
[docs/MAIL_RELAY_SETUP.md](docs/MAIL_RELAY_SETUP.md). Because the mail then
genuinely originates from the `doh.gov.ph` Workspace mailbox, Google handles
SPF/DKIM itself — which is also why the third-party-sender DNS authentication
we couldn't arrange is no longer needed.

Once live, restart/rebuild the Space and verify: invite a test account from
`/admin/users` and confirm the email arrives.

---

## Status

- [ ] 1. HF token rotated
- [ ] 2. `CSS_SESSION_SECRET`, `CSS_BASE_URL`, `CSS_SECURE_COOKIES` set on the Space
- [ ] 3. Pilot auth reverted to invite links (code shipped; deploy the mail relay — [docs/MAIL_RELAY_SETUP.md](docs/MAIL_RELAY_SETUP.md))
- [x] Cookie `Secure` support in code (`CSS_SECURE_COOKIES`, off by default) — shipped
# Candidate 7.28: browser write boundary

Staff writes and public account actions now require an exact Origin (or Referer fallback). Configure the canonical public origin and update native cookie-based clients. Public/bearer routes and signed machine callbacks have explicit exceptions with their own controls. Logout is POST-only for session revocation. See [request security policy and verification](docs/REQUEST_SECURITY.md).

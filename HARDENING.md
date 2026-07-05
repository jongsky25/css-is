# Pre-production hardening checklist

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

> Leave `CSS_DB` **UNSET** — see [DEPLOY.md](DEPLOY.md). This Space uses the
> DB-in-repo round-trip model; pointing `CSS_DB` at `/data` would silently break
> deploys. Do **not** enable persistent storage.

Confirm uvicorn runs with `--proxy-headers` (in the Dockerfile / start command)
so `request.base_url` and the Secure cookies see the real HTTPS scheme behind
HF's proxy.

After setting these, restart/rebuild the Space and verify: log in, redeploy, and
confirm you stay logged in (proves `CSS_SESSION_SECRET` is sticking).

---

## 3. Revert pilot auth → emailed invite links + SMTP  (code + your SMTP creds)

**Current pilot behaviour** (`auth.DEFAULT_PASSWORD = "12345678"` + `must_change`):
new/reset accounts get the known temp password, so anyone who knows the
convention can sign into a freshly-created account until the user sets their own.
Acceptable for an internal LAN pilot **only**.

To productionise (the invite-link machinery — `/set-password`, `mailer.py`,
`_invite_link` — already exists, it just isn't the active path):

1. Add SMTP secrets to the Space (Settings → Variables and secrets):
   `CSS_SMTP_HOST`, `CSS_SMTP_PORT` (587), `CSS_SMTP_USER`, `CSS_SMTP_PASS`,
   `CSS_SMTP_FROM`, `CSS_SMTP_TLS` (1).
2. **Code change (ask Claude):** switch account creation
   ([app.py](app.py) `~1070`) and "Reset password"
   ([app.py](app.py) `~1232`) to **email an invite/reset link** instead of
   setting `12345678`; point `/forgot` at the email flow rather than
   "contact your administrator."
3. Once live, stop handing out the default password entirely.

This one needs your real SMTP credentials to test end-to-end, so it's best done
when you're actually ready to cut over.

---

## Status

- [ ] 1. HF token rotated
- [ ] 2. `CSS_SESSION_SECRET`, `CSS_BASE_URL`, `CSS_SECURE_COOKIES` set on the Space
- [ ] 3. Pilot auth reverted to invite links + SMTP
- [x] Cookie `Secure` support in code (`CSS_SECURE_COOKIES`, off by default) — shipped

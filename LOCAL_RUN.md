# Run CSS-IS on your own machine + run the QA suite

> Why this file: the Cowork session could **not** run the app or the automated QA, because
> this sandbox receives **corrupted copies of the large source files** (`app.py`, `storage.py`,
> `dashboard_export.py`, `harmonize.py`) and a malformed copy of `css_is.db`. Your real files
> are intact — verified directly. On your own Windows machine there is no such corruption, so
> everything below works normally. See `STATUS_EXECUTION_2026-06-11.md` for the evidence.

## 1. Install dependencies (once)
```
cd path\to\css
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Start the app
```
python -m uvicorn app:app --reload --port 8000
```
Then open http://localhost:8000

**First run:** the database ships with **no admin accounts**, so the first login screen
*creates* the first administrator — enter your email and a password (≥ 8 characters). After
that, you're logged in as admin and can invite the rest of the team from **Admin → Users**.

**On the office Wi-Fi (QR codes):** respondents scan a QR that points at
`http://<your-LAN-IP>:8000/r/<token>`, so the PC running this must be reachable on the same
network. If the detected address is wrong, set it before launching:
```
set CSS_BASE_URL=http://192.168.x.x:8000   &  python -m uvicorn app:app --port 8000
```

## 2b. Deploy to an online staging / production site

All absolute links and QR codes are built per-request by `_base_url(request)` — there is
**no hard-coded host** anywhere. The basis is always the URL the app is reached on, so the
same build works on localhost, a LAN IP, or any public domain. Two things make it correct
behind a hosting platform / reverse proxy:

1. **Pin the public domain** so QR codes (which get printed) and emails always use one stable,
   canonical address — and so a forged `Host` header can't redirect your links:
   ```
   set CSS_BASE_URL=https://your-staging-domain      (Windows)   # no trailing slash needed
   export CSS_BASE_URL=https://your-staging-domain   (Linux/host platform env var)
   ```
2. **Trust the proxy headers** so the app sees the real `https://` scheme + public host that the
   HTTPS terminator forwards (without this, the app would think it's plain `http` on an internal
   host). Launch single-process (the in-process cache requires `--workers 1`):
   ```
   python -m uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1 \
          --proxy-headers --forwarded-allow-ips="*"
   ```

With both set, every QR code, "Copy link", event/registration link, and email link resolves to
the public URL automatically. If you *don't* set `CSS_BASE_URL`, the app falls back to whatever
origin the request arrived on (still correct with `--proxy-headers`); a localhost request falls
back to the LAN IP so dev QR codes stay phone-scannable.

> **Also flip the session cookie to `Secure` on HTTPS** (see §5) — staging is the trigger for it.

## 3. Run the QA gate + tests (do this BEFORE trusting a build)
```
python qa_preflight.py            # integrity gate: must print "RESULT: GREEN"
python -m pytest                  # routes / auth+RBAC / input-abuse / integrity / new modules
python qa_smoke.py                # dashboard data + every export format (no time limit locally)
```
`qa_preflight.py` is the keystone — it compiles every module, imports them, parses every
template, and sweeps for the truncation signature. **If it prints RED, do not ship that build.**
A RED here on your machine would mean a genuinely truncated file (unlike the Cowork sandbox,
which corrupts on read); restore it and re-run.

## 4. Point at your real data / roll back
- The app reads `css_is.db` from the project folder. Keep your live DB there.
- Code backups from QA work are under `_backups/qa_*/`. To roll a file back:
  `copy _backups\qa_<timestamp>\app.py.orig app.py`
- The database is never modified by the test suite (tests run on a throwaway copy).

## 5. Known non-defects (from the QA review)
- **0 admin users by design** until first-run setup (above).
- **Session cookie is not `Secure`** — intended for LAN/HTTP use. If you ever expose this beyond
  the office network, put it behind HTTPS and set the cookie `Secure`.

## Optional public short links

Automatic is.gd shortening is off by default. See [SHORT_LINKS.md](docs/SHORT_LINKS.md)
for `CSS_SHORT_LINKS=1`, canonical HTTPS origin requirements, queue behavior and the
resumable active-activity backfill. No is.gd account or key is required.

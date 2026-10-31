# Private Hugging Face preview — setup step 4

Target: `equityinhealth/office-connect-preview`, separate from the production
`equityinhealth/office-connect` Space. Hosting choice explicitly confirmed by the
user on 2026-10-31. No Render resource was created.

## Current status

Published on 2026-10-31 and verified **RUNNING** on CPU Basic. Authenticated
metadata confirms private visibility and Docker SDK. `/preview-health` returns
200 with the expected readiness text; `/login` returns 200 with the PREVIEW banner
and preview environment header. Anonymous requests to both return 404.
Source commit: `f03125c2d56e9f6f4f029e77ef821d91be46d076`.
Space commit: `5ac1982785c0298e0e9203c084a465f6d1ead53d`.

The preview password secret exists remotely; its value was not read or changed.
The owner’s iPhone Safari screenshot on 2026-10-31 confirms successful login,
the signed-in synthetic administrator home page, and the PREVIEW banner within
the private Hub frame. A subsequent screenshot confirms Calendar navigation and agenda rendering.
Step 4 phone acceptance is complete; this does not verify all features or data
writes. Safari private-Space cookie limitations remain as documented below.

The current [Spaces overview](https://huggingface.co/docs/hub/spaces-overview) and
[hardware guide](https://huggingface.co/docs/hub/spaces-gpus) were read on 2026-10-31.
CPU Basic has no hourly hardware charge, but creating a compute-backed Docker
Space requires an eligible account plan. Verify the account's eligibility in the
Dashboard; this setup does not purchase or upgrade any plan/hardware/storage.

## One-time access setup

1. In [New Space](https://huggingface.co/new-space), select owner **equityinhealth**,
   name **office-connect-preview**, **Docker**, **Private**, and **CPU Basic**.
   Create a blank Space, not a duplicate of production. Do not select paid hardware
   or attach production storage. If account eligibility prevents creation, report
   that limitation before considering any paid option.
2. In that preview Space's **Settings → Variables and secrets**, create a **secret**
   named `OFFICE_PREVIEW_PASSWORD`, choosing a new password of at least 16 characters.
   Keep it in your password manager; do not reuse your production password or post
   it in chat. This is the synthetic app account's password, not an HF token.
3. Create a [fine-grained Hugging Face token](https://huggingface.co/settings/tokens)
   with write access to **only this preview Space**. Store it as `HF_TOKEN` using
   the cloud environment's supported secret configuration. Do not paste it into chat or commit it. The publisher requires
   `HF_TOKEN`; a cached login alone does not satisfy its explicit credential check.
   If secret configuration is unavailable in the client, report the missing access
   instead of placing credentials in source or invoking production workflows.

The publisher can also create the private Docker Space when an appropriately
scoped credential allows it, but the recommended fine-grained setup above gives
access only to the existing preview repository. The preview app secret can
alternatively be supplied through a separate cloud secret named
`OFFICE_PREVIEW_PASSWORD`; the publisher sets it on the preview Space without
printing it. Production GitHub Action secrets cannot be read back and are not used.

## Publish from the cloud

Use an isolated deployment-tool environment and the existing hashed deploy lock:

```bash
uv venv --python 3.11 --seed /tmp/office-preview-deploy
/tmp/office-preview-deploy/bin/python -m pip install --require-hashes --only-binary=:all: -r requirements-deploy.txt
python scripts/deploy_preview_hf.py
/tmp/office-preview-deploy/bin/python scripts/deploy_preview_hf.py --publish
```

The default command is a dry run and makes no Hugging Face requests. Publishing
requires a clean, committed working tree. The target is fixed to the preview
Space; a public target is rejected. The publisher sets no hardware upgrades and
never calls `deploy_hf.py` or its production backup/download/upload routine.

The bundle selects the production runtime Python closure without importing the
production deployment script. It includes tracked templates/static assets/logos,
the dependency lock and a special preview Dockerfile/entrypoint. It excludes
databases, backups, local env files, logs and production deploy credentials.
Only staged copies of templates get a visible **PREVIEW** banner. Source templates
and the production Dockerfile are unchanged. `preview-build.json` records the commit.

## Review from your phone

Once the build is running, open the preview Space in Hugging Face while signed
into an account allowed to access the private Space. Its intended hub URL is
`https://huggingface.co/spaces/equityinhealth/office-connect-preview`.

App username: **preview@example.invalid**. Use the password stored in the preview
Space secret. All records are synthetic; initially it contains only that admin and
the standard organization structure. Create fake activities/requests for review.
Everything resets on process restart, including sessions. There is no persistent
disk/bucket or production database. This is a review environment, not a backup.

Background scheduling is disabled, inherited integration credentials are removed,
and the Python/asyncio socket path rejects external connections. The latter is
a guard for this application, not an OS-level network sandbox; native subprocesses
are not confined by Python hooks. Do not enter real integration keys, personal
data, or production settings in the preview. Missing app password fails startup
rather than opening first-admin registration to visitors.

## Verification before marking complete

- Confirm remote Space ID, private visibility and CPU Basic hardware.
- Monitor the build until running; upload acceptance alone is not success.
- Confirm an unauthorized visitor cannot access the private app.
- Confirm the deployed commit from `preview-build.json`.
- Through authorized access, check `/preview-health`, the PREVIEW banner, wrong
  password rejection, and a successful mobile-sized login and page action.
- Confirm no production data/storage/integration secrets were copied.
- Record the observed URL, commit, build state and limits in `SETUP_STATUS.md`.

Local tests: `tests/test_preview_setup.py` stages and boots the actual bundle,
verifies failed/correct login through HTTP, signs in using a 390×844 Chromium
viewport, checks the visible banner, confirms a sentinel database is untouched,
and verifies external connections are rejected. Both tests passed without skips.
Local success does not establish remote hosting, private access, or account eligibility.

## Private Space embedding on iOS

The preview entrypoint permits framing by `https://huggingface.co` and removes
its `X-Frame-Options` header. Hosted preview cookies use `SameSite=None` while
retaining Secure/HttpOnly and the application's origin checks, so the Hub frame
can retain the synthetic login. These exceptions apply only to the disposable
preview; production response policy is unchanged.

Safari may still require temporarily disabling Prevent Cross-Site Tracking for
Hugging Face's private-Space cookies. A direct `.hf.space` URL alone does not
establish private Hub authorization. Use the signed-in Hub page for phone review;
never put the HF token into a URL or browser instructions.

# Deployment & live-data rules

## Current repair-release guidance — October 19, 2026

Use [Phase 0 repairs and rollout](docs/PHASE0_REPAIRS.md) for release 7.23. The deployed storage configuration is **not yet verified**. When `CSS_PERSIST_DIR` is set, the application keeps its live SQLite database at `CSS_DB` (default `css_is.db`), restores a bucket snapshot on boot and snapshots back every configured interval. The bucket is not necessarily the live database path. Confirm effective paths before deploying or restoring anything.

Release 7.23 adds revocable sessions and requires fresh sign-in; database restores also invalidate sessions. Merging to `main` deploys automatically, so keep the repair on its review branch until the production verification gate in that runbook is complete.

> ## ⛔ THE WHOLE ROUTINE
>
> **As of the `deploy-hf.yml` push trigger, merging a PR to `main` ships it —
> automatically.** The GitHub Action runs the exact same `deploy_hf.py` routine
> described below, using `CSS_ADMIN_USER`/`CSS_ADMIN_PASS`/`HF_TOKEN` secrets for
> the parts that used to need a human at a keyboard. It still hard-aborts
> (`CSS_DEPLOY_STRICT_VERSION`) if a merge forgot to bump `APP_VERSION` — bump the
> version on every user-visible PR, same as always, or the auto-deploy fails loudly
> instead of silently shipping unversioned. Watch the run: Actions → "Deploy to
> Hugging Face".
>
> For a manual / local / retry deploy (e.g. `--skip-backup`, or shipping without a
> PR), the old routine still works:

```
# 1. Build your change; bump version.py (APP_VERSION) + add a CHANGELOG.md line; run tests.
# 2. In the live app: Admin → Backups → Download  (saves css_is_<ts>_*.db to ~/Downloads)
# 3. Ship:
python deploy_hf.py        # finds that download, shows it, asks one Y/n, then deploys + verifies
```

No `git push` needed for the local routine — the GitHub mirror's history is
separate from the Space's (see below). The CI-triggered deploy is the one
exception: it deploys straight off whatever's on `main`, so for that path
merging IS the ship step.

> ⚠️ **Doc/reality check needed:** a July 17, 2026 deploy run logged
> `Persistence is ACTIVE (CSS_PERSIST_DIR set): the live DB lives on the bucket;
> shipping code only — skipping the frozen css_is.db seed.` That's the
> **persistent-storage model** this file's "Alternative model (NOT in use)"
> section (bottom) says is *not* what's live — but the log says otherwise. Until
> someone confirms which model the Space is actually running, don't trust this
> file's DB-handling sections (the live-data rule, the backup-download step, the
> "CSS_DB UNSET" config) at face value.

## Why `upload_folder`, never `git push`

The local repo and the Space's git repo have **completely separate histories** (no
common ancestor), because every deploy is a server-side upload. So a `git push space
main` is **rejected**, and a `git push --force space main` would **WIPE the live
Space**. `upload_folder` (what `deploy_hf.py` runs) instead adds one commit **on top
of** the Space's current state — additive, preserving server-side files
(`.session_secret`, anything you didn't upload). It is the only method that has ever
worked here. The `space` git remote is for *reading* only (`git fetch space`).

## What `deploy_hf.py` does

1. **Pulls the live DB.** Finds the newest `css_is_*.db` in `~/Downloads`, shows its
   timestamp + response count next to your current local DB, and — after one Y/n
   (auto-yes when run with `--yes` or backgrounded) — backs up the current DB to
   `_backups/…_predeploy.db` and swaps the downloaded one into `css_is.db`. This
   **replaces the old manual copy step.** If no download is found, or the local DB is
   already newer, it ships the local DB unchanged.
2. **Guards the version bump.** Aborts (with a confirm) if the live site already shows
   `APP_VERSION` — i.e. you forgot to bump `version.py`.
3. Uploads the runtime closure (`ALLOW` in the script) + `version.py` + `css_is.db`,
   waits for `RUNNING`, then verifies `/login` shows the expected version.

`deploy_hf.py` is the single source of truth for *what* uploads — change it, don't
hand-roll `upload_folder` elsewhere. **Auth:** HF token cached at
`~/.cache/huggingface/token` (user `equityinhealth`); `HfApi()` picks it up.

> ⚠️ `build_hf_upload.ps1` is a DIFFERENT, **deprecated** model (omits `version.py`
> + `css_is.db`, assumes `/data` persistence this Space does not use). Do not use it.

## The live-data rule (why the pull matters)

The Space serves exactly the `css_is.db` you upload (`CSS_DB` is unset, so the app
reads the repo DB). **Any edit made on the live site after your last pull is lost on
the next deploy** (and on any HF rebuild/sleep, which restores the last-uploaded DB).
So always download a fresh backup right before deploying — `deploy_hf.py` automates
the swap, but only from a file *you* downloaded, so the download must be current. This
is how Spot Feedback tags were lost once: a stale DB was shipped.

> The local DB is easily dirtied by running the app (logins, audit rows, atoms WAL).
> Let `deploy_hf.py` pull a fresh live DB rather than shipping one polluted by local
> test sessions. To reset manually: remove `css_is.db-wal`/`-shm`, then restore a
> known-good DB.

## Verify the effective storage model

The historical DB-in-repository instructions above describe an earlier deployment model. The current deploy script detects `CSS_PERSIST_DIR` and can upload code without the seed database. Confirm the actual Space variables/mounts before following the historical download-and-upload routine; do not change storage topology based on this document alone.

An ephemeral deployment without verified durable storage can lose data on rebuild. Its startup warning is actionable. Keep the signing secret configured, use the correct public base URL, secure cookies and proxy settings, and verify recovery from a real snapshot. A stable signing secret does not override session revocation or the deliberate fresh-login requirement after database restoration.

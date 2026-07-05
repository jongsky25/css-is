# Deploy from your phone

You can change the app and push it live to Hugging Face using **only the GitHub
mobile app** (or github.com in a phone browser) — no computer needed. There are
two parts: make your edit, then tap the deploy button.

## One-time setup (do this once, on any device)

The deploy button runs on GitHub's servers, so it needs three repo secrets.
In **Settings → Secrets and variables → Actions → New repository secret**, add:

| Name | Value |
| --- | --- |
| `HF_TOKEN` | A Hugging Face **write** token for user `equityinhealth` |
| `CSS_ADMIN_USER` | The app's admin username (for the pre-deploy backup gate) |
| `CSS_ADMIN_PASS` | The app's admin password |

If these are missing the deploy stops with a clear error and nothing ships.

## Every deploy — the two steps

### 1. Make your change

In the GitHub mobile app: open the file → ✏️ edit → **Commit changes**.
(Skip this step if you only want to re-deploy without a code change — but note
every deploy still bumps the version, so there's always *something* new.)

### 2. Tap Deploy

1. Open the repo → **Actions** tab.
2. Tap **"Deploy to Hugging Face"** in the workflow list.
3. Tap **Run workflow**.
4. Fill in the form:
   - **What changed?** — one plain sentence, written for the people who use the
     system (it becomes the "What's new" note on the sign-in screen).
   - **Version step** — `minor` for a normal change/fix, `major` for a big
     release. Leave it on `minor` if unsure.
   - **skip_backup** — leave **off**. (Only turn on if the backup system itself
     is broken and you accept the risk.)
5. Tap the green **Run workflow** button.

That's it. Watch the run turn green (a couple of minutes). You'll see the live
site show the new version and your "What's new" note.

## What the button does for you

You don't edit `version.py` or the changelog by hand — the workflow does it:

1. **Bumps the version** and writes your sentence into the sign-in "What's new"
   list *and* the technical `CHANGELOG.md` (`bump_version.py`).
2. **Deploys** — the same routine as the desktop `deploy_hf.py`: it secures a
   fresh, verified backup of live data first, then uploads the code to the
   Space and waits for it to come back up.
3. **Saves the version bump back to the repo**, but only if the deploy
   succeeded — so the code and the live site never drift apart.

## Good to know

- **Nothing deploys on its own.** A commit from your phone just sits there until
  *you* tap Run workflow. So editing on mobile is safe.
- **Live respondent data is safe.** The database is not shipped from GitHub — it
  lives on the Hugging Face side — so a mobile deploy ships code only and never
  overwrites people's responses.
- **If a deploy fails**, read the red step's log. The usual causes are a missing
  secret (see setup above) or the backup gate not being able to reach the live
  site. Fix it and tap Run workflow again — the version isn't advanced until a
  deploy actually succeeds, so re-running is safe.
- **Big edits are painful on a phone.** This path is best for small fixes and
  copy tweaks; for large changes, use the desktop flow in `DEPLOY.md`.

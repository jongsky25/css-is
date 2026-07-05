# build_hf_upload.ps1
# -------------------------------------------------------------------------
# ⛔ DEPRECATED — NOT THE DEPLOY PATH. Do NOT use this to deploy.
#   * It belongs to the persistent-storage (/data) model that this Space does
#     NOT use, and it deliberately OMITS css_is.db AND version.py.
#   * The live deploy is:  python deploy_hf.py   (huggingface_hub upload_folder).
#   * NEVER git push to the `space` remote (disjoint history → force-push wipes it).
#   See DEPLOY.md.
# -------------------------------------------------------------------------
# (Original purpose, kept for the alternative model only:)
# Assembles a CLEAN folder ("hf_upload") containing ONLY the files the
# Hugging Face Space needs to run. Re-run this any time before uploading;
# it wipes and rebuilds the folder from the current source so the upload is
# always in sync with your code.
#
#   Usage:  right-click > Run with PowerShell   (or)   .\build_hf_upload.ps1
#
# Then drag the CONTENTS of hf_upload\ into the HF Space "Files" web uploader.
# -------------------------------------------------------------------------

$ErrorActionPreference = "Stop"
$src = $PSScriptRoot
$out = Join-Path $src "hf_upload"

# Runtime Python modules actually imported by the app (verified import closure).
$pyFiles = @(
    "app.py",
    "css_is_engine.py",
    "storage.py",
    "tzutil.py",           # single source of local (PH) wall-clock — imported everywhere
    "fix_timezone_history.py",  # one-time migration to fix pre-fix UTC time logs (run on /data)
    "dashboard_insights.py",
    "dashboard_export.py",
    "dashboard_docs.py",
    "report_docs.py",
    "csm_report.py",
    "auth.py",
    "mailer.py",
    "backups.py",
    "retention.py",
    "monitoring.py",
    "name_cleanup.py",
    "apply_speakers.py",   # imported by name_cleanup.py
    "harmonize.py",
    "activity_admin.py",
    "activity_messages.py",
    "certificate.py",
    "ratelimit.py"
)

# Deployment / config files HF needs.
#
# NOTE: css_is.db and .session_secret are DELIBERATELY NOT shipped. The HF Space
# repo can be public, so neither live respondent data nor the session-signing
# secret may travel inside it.
#   * Live data lives on persistent storage (/data/css_is.db via CSS_DB). On a
#     brand-new Space the app self-initialises a clean schema + seeded directory
#     on first request (get_conn -> init_db + seed_directory_if_empty), so no
#     seed file is needed. To pre-load real data, upload a DB straight to /data
#     (Dev Mode / SSH), never through the repo.
#   * The signing secret comes from the CSS_SESSION_SECRET Space secret
#     (Settings -> Variables and secrets); auth.py reads it before the file.
# See DEPLOY.md.
$deployFiles = @(
    "Dockerfile",
    "requirements.txt",
    "README.md"           # HF Space front-matter (sdk: docker, app_port: 7860)
)

# Folders copied whole.
$folders = @("templates", "static", "assets")

# --- rebuild from scratch ---
if (Test-Path $out) { Remove-Item $out -Recurse -Force }
New-Item -ItemType Directory -Path $out | Out-Null

$missing = @()

foreach ($f in ($pyFiles + $deployFiles)) {
    $p = Join-Path $src $f
    if (Test-Path $p) {
        Copy-Item $p (Join-Path $out $f) -Force
    } else {
        $missing += $f
    }
}

foreach ($d in $folders) {
    $p = Join-Path $src $d
    if (Test-Path $p) {
        Copy-Item $p (Join-Path $out $d) -Recurse -Force
        # strip any __pycache__ that rode along
        Get-ChildItem (Join-Path $out $d) -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
            Remove-Item -Recurse -Force
    } else {
        $missing += "$d\"
    }
}

# --- report ---
$count = (Get-ChildItem $out -Recurse -File).Count
$size  = "{0:N1}" -f ((Get-ChildItem $out -Recurse -File | Measure-Object Length -Sum).Sum / 1MB)
Write-Host ""
Write-Host "Built: $out"
Write-Host "  $count files, $size MB total"
if ($missing.Count) {
    Write-Host ""
    Write-Host "WARNING - these expected items were not found:" -ForegroundColor Yellow
    $missing | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
}
Write-Host ""
Write-Host "Next: upload the CONTENTS of hf_upload\ to your HF Space (Files tab)."

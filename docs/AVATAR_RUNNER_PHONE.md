# Run the cloud diagnostic from your phone

No Linux device, terminal, SSH client, or app credentials are needed.

The setup pull request runs the diagnostic once through its **Checks** tab. After
this workflow is registered on the default branch:

1. Open this repository at github.com in your phone browser and sign in.
2. Open **Actions → Avatar cloud runner diagnostic → Run workflow**.
3. Select **main**, then tap **Run workflow**. You may close the browser while it runs.
4. Open the completed run for its plain-language summary. Under **Artifacts**, tap
   **avatar-runner-diagnostic** to download the complete results, including failures.

If the controls are hidden, enable **Desktop site** in your phone browser. The
GitHub mobile app may expose fewer workflow controls than the browser. You need
repository permission to run Actions, and Actions must be enabled. Standard hosted
runner availability and included minutes depend on your GitHub repository/plan;
this workflow does not configure paid or larger runners.

The diagnostic is pinned to a specific reviewed commit. It runs four synthetic
controls on a standard Linux x64 GitHub runner and reports scheduling context.
It does not prove physical-host isolation, qualify 2B, compare app candidates, or
deploy. All earlier failed measurements remain failed. An unavailable pinned
browser/dependency stops setup; it is not silently replaced.

Do not use **Re-run jobs** to replace a failure or obtain a more favorable sample.
Keep that run's logs and results for investigation. The workflow saves artifacts
for 30 days; download them if you need a durable copy.

This setup PR only adds the workflow and these instructions. It does not merge
the avatar verification branch. Existing repository release checks still apply
to merging; this setup does not bypass them or modify the auto-deploy workflow.

## Native-recorder calibration

The separate **Avatar native recorder calibration** workflow runs fresh native
proofs, then exactly four control/probe/probe/control measurements. Its artifact
is **avatar-native-calibration**. A passing calibration permits only a separately
planned application measurement; it is not 2B acceptance. Keep both failed and
successful runs. The setup PR validates this workflow once before registration.

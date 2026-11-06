# Native recorder calibration from your phone

The setup PR runs one complete calibration when it opens. Open its **Checks** tab,
then **Native recorder calibration** for the summary and artifact link. You can
close your browser while GitHub works; no Linux device or SSH is needed.

After this workflow is registered on main, open **Actions → Avatar native recorder
calibration → Run workflow**, select main and confirm. Download the
**avatar-native-calibration** artifact from the completed run. Enable Desktop site
in your phone browser if workflow controls are hidden.

The workflow first proves the native recorder and receiver identities. Only if
both pass does it run exactly four control/probe/probe/control measurements. All
fixed costs, stability, source-identity and natural-reclamation gates remain.
Every result and failure is retained, with no automatic retry or application run.
Do not use Re-run jobs to seek a better result. A passing instrument calibration
is not application acceptance or a deployment.

Only this workflow and guide are proposed for main. Existing release checks apply;
this PR does not change app versions, bypass those checks or deploy. Its opened-only
PR trigger prevents later documentation pushes from repeating measurements.

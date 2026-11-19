# Documents: real-device validation and usability session

Prepared after the Division follow-up candidate 10.39. No physical-device,
VoiceOver or staff usability session has been performed. Automated Linux WebKit
success is supporting evidence, not a substitute for these sessions.

## Session setup

Use the private synthetic preview described in [the mobile workflow](MOBILE_CLOUD_WORKFLOW.md)
and [preview setup](HF_PREVIEW_SETUP.md). Record the exact preview commit/version
and verify its banner before starting. Do not use production records or send real
notifications. A preview must contain the Division filter candidate before that
journey can be assessed; no new preview was published for this checklist.

Record iPhone model, iOS/Safari version, text-size setting, orientation, VoiceOver
state, tester role and date. Use synthetic accounts representing a contributor and
a division chief/OIC, with restricted records belonging to another account.

## Tasks and acceptance criteria

| Task | Observable result |
| --- | --- |
| Open My next steps and choose Waiting | Counts and visible cards agree; selected filter is announced and retained. |
| Open a request, its linked work and return | Back links have meaningful names and restore the same queue/filter/page. |
| Review a changed request without confirming | Native validation prevents the write; source and work remain unchanged. |
| Confirm review using a synthetic record | Success is announced; a history entry appears without changing work contents. |
| Navigate Older reviews and Latest reviews | Entries beyond 20 are reachable, newest labeling is correct, and focus remains usable. |
| Open Division follow-up, select a state and Overdue only | Counts cover permitted exceptions; Next page and document return retain the filters. |
| Switch to an account without division authority | Division access is denied; restricted records and private work are not exposed. |
| Repeat navigation with larger text and portrait orientation | Content wraps without page-wide horizontal scrolling; controls and labels remain readable. |
| Repeat key journeys with VoiceOver | Controls have useful names/roles/states; order follows the task; errors and results can be found; no focus trap. |

For VoiceOver, use native swipe navigation and rotor headings/links/forms. Check
both touch activation and an external keyboard if available, recording which was
actually used. Do not count an untested input method as passed. Record any Safari
private-preview authentication limitation separately from application behavior.

## Small usability session

Use the same synthetic task set for each participant. Have each person identify
what they should do next, find a waiting item, recover their queue after reviewing
a document, and locate an older review. A chief/OIC also filters division follow-up.
Record completion, elapsed time, wrong turns, assistance and the participant's
own description of confusing wording. Do not claim improvement without a comparable
baseline using the same tasks and roles. No staff invitations are authorized by
this preparation document.

## Results sheet

| Date / preview commit | Device / role / input method | Task | Pass / fail / not run | Time / assistance | Finding / reproduction |
| --- | --- | --- | --- | --- | --- |
| Not run | Not run | All tasks | Not run | Not measured | Physical device and participant sessions outstanding |

Save only synthetic examples and non-identifying observations. For a failure,
record the starting page/filter, exact steps, expected and observed behavior,
and whether it reproduces with VoiceOver off. Link a scoped follow-up issue/PR
when a fix is needed, then retest the same task. Authentication/access blockers,
critical task failures and unknown results remain open rather than being marked
accepted. This checklist does not authorize production changes or external contact.

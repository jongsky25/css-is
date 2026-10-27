# MCP personal saved report views — M2.4

Implemented for v8.82; independently disabled by default. Hosted acceptance is
pending. Follows private comment drafts merged in
[PR #492](https://github.com/jongsky25/css-is/pull/492) and the
[common confirmation/receipt contract](MCP_WRITE_PILOT.md).

## Exact capability

`prepare_saved_report_view(name, report_type, year, operation_id, month=None,
quarter=None)` prepares a new owner-private named report selection:

- `csm_month`: one month (1–12), with no quarter. The link selects the existing
  bureau-wide Type 1 report by inclusive submission dates, including leap days.
- `activity_quarter`: one quarter (1–4), with no month. The link selects the
  existing bureau-wide Type 2 report using `quarter:YYYY-Qn`.

Years are 1900–9998. Names are 1–60 characters on one line, trimmed, with control
characters rejected. Strict integer validation rejects boolean/string period
values. Mixed/missing period fields, unknown types, arbitrary dates/URLs,
office/activity/person filters and other fields are refused. Source URLs are
generated on the server from those fixed fields, never accepted from a client.

This stores preferences, not survey data. It does not read/cache scores,
responses, comments, identities or demographics; change surveys; generate or
publish a report; create a download; or edit/delete another selection. No
existing survey-read grant is broadened. Report data and current permissions
are applied only when the person opens the ordinary report screen.

The preview shows the exact name, report type, year/month or quarter and a local
source link. No view is saved until the user clicks **Confirm: save my report
view** in the signed-in browser. Afterwards, **Reports → My saved report views**
lists only that owner's selections. Each source page links to the exact report
period and explains that the data remains current, not a stored results snapshot.

This first pilot is create-only and limited to ten saved selections per person.
Names use the existing SQLite case-insensitive uniqueness convention. No rename,
overwrite, delete, sharing, Type 3/person view or arbitrary-filter tool is added.
Preference management beyond this bounded creation pilot is separate work.

## Action contract

- New `reports:view:save` consent is excluded from default OAuth scopes. Ordinary
  report reads and other draft-action scopes cannot save report views. Existing
  grants and refreshes remain unchanged.
- `CSS_MCP_ENABLED=1` and independent `CSS_MCP_REPORT_VIEWS_ENABLED=1` govern the
  MCP pilot. Survey summary switches and other write switches are not required:
  saving preferences does not invoke their aggregate tools or read survey data.
- Recheck the current active account and normal Reports `view` capability. The
  preview binds actor, exact grant/resource, normalized selection digest,
  internal operation key and ten-minute expiry. This creates a selection rather
  than updating a report, so no survey/data revision is claimed or frozen.
- Before saving, recheck permission, scope, switches, expiry, payload integrity,
  name absence and the ten-view limit under the writer lock. A name taken or
  capacity filled by another tab produces a conflict instead of an overwrite.
  Origin, registered-session CSRF and exact preview-digest checks protect POST.
- The private selection, original operation receipt and body-free audit commit
  atomically. Audit failure rolls everything back. Concurrent/repeated calls and
  confirmations recover one original view. A changed selection or different
  connection cannot reuse a key. A completed receipt is not revalidated as a
  new-name creation, so recovery still works after the name/limit is occupied.
- `get_saved_report_view_operation(operation_id)` recovers the original status
  and private source link through the same active grant without returning
  labels or report data. Stable grant identity survives token rotation. Grant,
  account/scope/session revocation and historical restore block pending saves.
- Saved collection/source pages require a current registered session, owner
  match and report-view capability. They remain normal user preferences after
  the MCP pilot is disabled or disconnected. They use private/no-store headers.

Keep a random 16–80 character key across timeouts. An unavailable response is
not proof of no commit: inspect the original receipt/source before creating a
replacement key. Operation namespaces/recovery tools are separate from earlier
pilots. Each actor may have 50 unexpired pending previews and 10,000 total keys.
Completion clears duplicate preview metadata. Entry points commit bounded lazy
cleanup of up to 100 expired payloads, retaining key/hash/ID/time tombstones.
Lazy cleanup is not timed deletion on an idle host; wider rollout needs retention
maintenance. Names and periods are not copied into action audit summaries.

## Operator pilot

1. Deploy v8.82 or later and record running version/commit. The runtime package
   includes `report_views.py` and `mcp_report_views.py`; import-closure tests must
   pass. Enable global MCP and `CSS_MCP_REPORT_VIEWS_ENABLED=1`, then restart.
2. Refresh ChatGPT's tool catalog for `prepare_saved_report_view` and
   `get_saved_report_view_operation`. Reauthorize and explicitly approve the new
   saved-report-selection permission. Check readiness.
3. With an agreed test account, prepare a September 2026 CSM selection or a
   Q3 2026 activity selection. Review its name and period/source link in the
   browser. Confirm no saved view exists before confirmation.
4. Confirm the save. Compare the private source page and Reports collection with
   the exact report query/period. Opening the report should use current source
   data; the saved-view tool should return no scores, responses or exports.
5. Repeat/recover the key and resubmit the form: one selection remains. Test a
   duplicate name, a name taken after preview, the ten-view limit, another user,
   missing action permission, expiry, changed payload and revoked session/grant.
6. Record version/SHA, role, source-selection parity, denial/recovery observations
   and latency before recording hosted acceptance. Local coverage includes real
   OAuth/MCP/browser confirmation across token rotation and a mobile no-script
   save/source/collection flow. Hosted acceptance remains pending.

Disable `CSS_MCP_REPORT_VIEWS_ENABLED` and restart to block MCP preparation,
confirmation and receipt disclosure. Revoke the test connection to invalidate
its previews permanently. Re-enabling may resume an unexpired preview. Saved
preferences remain accessible to their current owner; rollback does not delete
or reverse them through MCP.

# Preview loading correction candidate

When an editor requests an updated private preview, set the iframe to eager
loading before changing its URL. This allows both the Update preview button and
the automatic change handler to load a preview outside Chromium's lazy-load
margin. The initial iframe remains lazy. The script cache version advances to 3.

The real HTTP regression test deliberately moves the iframe 10,000 px below the
viewport and verifies four outfit updates without scrolling to the iframe, for
both manual and automatic updates. Both cases time out on unchanged source;
both pass with this correction. The final run passes all 24 selected checks:
the two regressions, appearance route/storage tests, and existing browser flows.

The first combined run used the July performance-fixture date and failed two
October scheduling expectations. Its full log is retained; rerunning with the
suite's normal October clock passes. The correction did not change between runs.

This is a separate candidate on `codex/avatar-preview-loading`. It is not included
in observer run 40323560666 and does not establish the cause of its predecessor's
historical timeout. It has not passed a full memory acceptance gate or been merged
into the primary verification branch. 2B remains blocked pending that work.

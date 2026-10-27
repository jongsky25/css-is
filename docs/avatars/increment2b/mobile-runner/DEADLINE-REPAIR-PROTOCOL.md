# Fixed-wait implementation repair after retained cloud captures

Workflow ab479b9 / harness c76ae40 on Python 3.12.14 captures all four controls.
Audit verifies twelve files and rejects three timer calls: slot1/doc6 219.660405ms,
slot2/doc9 219.973213ms, slot3/doc5 219.629035ms. A browser timeout requested at
220ms is not an implementation of a guaranteed host-monotonic 220ms minimum.
Raw controls and failure artifact 12733632971 remain; no record is discarded.

Preserve the >=220ms checker floor. In the separately versioned control diagnostic
v2, perform the original browser wait, then sleep only a positive remainder of the
host-monotonic deadline. Record requested padding per document; no padding if the
API already completes after the deadline. Negative tests retain shortened-wait
rejection; deterministic tests verify early and completed API cases. This does not
relax a budget or add unbounded warmup. Ordinary lifecycle v12 remains unchanged
when diagnostic timing is absent. Historical v1 audits retain their failed results.

Freeze the source and update the PR's exact checkout before the corrected cloud
attempt. Retain all four fresh slots in that attempt; no unchanged rerun, automatic
qualification or favorable replacement. Preserve the initial mismatched-container
failure and this complete failed diagnostic alongside all later captures.

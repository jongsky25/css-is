# V4 calibration failed the individual-pause gate

All four fixed workloads completed, all six trace segments are intact, and sealed
checkpoints match raw measurements. Audit verifies 116 source/probe hashes and
30 files; extracted archive re-audit is identical. Twenty-four focused tests pass.
Both traced slots exceed the unchanged 250ms individual-pause limit. All data and
failed gates remain in calibration.json; no v4 source comparison was launched.

The first traced slot's total explicit pauses fall to 3.912% of navigation time,
but the ten-navigation stop/drain/start pause is 322.947ms. Fewer rotations reduce
total work but transferring a larger trace during the remaining rotation still
stalls navigation. V5 will defer all trace stream transfers until AFTER measurement,
retaining the same segmentation, buffer, categories, endpoint-only dump and gates.
This requires a NEW fixed calibration; v4 samples are not reused or replaced.
Product and 2B disposition are unchanged.

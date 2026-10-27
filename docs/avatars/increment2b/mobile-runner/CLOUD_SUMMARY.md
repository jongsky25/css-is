# Cloud runner diagnostic

This checks the new GitHub runner. It does not accept 2B or deploy the app.

**Result: hosted diagnostic complete**

| Control | Duration (ms) | CPU steal context |
| --- | ---: | ---: |
| 1 | 3900.75 | 0.00% |
| 2 | 3818.16 | 0.00% |
| 3 | 3845.51 | 0.00% |
| 4 | 3893.63 | 0.00% |

CPU steal is shared CPU context, not an adjustment to durations.

Download the **avatar-runner-diagnostic** artifact for all raw results, including failures.
The earlier failed calibration remains failed. No automatic retry or application comparison follows.

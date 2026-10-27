# Driver identity repair after all four v1 initialization failures

Frozen d867258 attempted all four prescribed slots. All fail before begin_ns and
before any measured phases. Read-only reproduction isolates the missing path:
/proc/<python>/task/<python>/children is absent in this runtime. Other required
/proc stat/schedstat, cgroup cpu.stat/cpu.max, load and aggregate CPU files read.
All four captures, identity traces and errors are retained in the v1 failure archive;
none is a timing observation and no favorable replacement run is claimed.

Repair only driver identity lookup: use pinned Playwright PipeTransport's existing
asyncio subprocess PID; require /proc/<pid>/stat parent PID equals this Python PID.
No process-wide scanning, command lines or environment reads. Preserve protocol,
four fresh uninjected slots, fixtures and full phase/CPU capture policy. Separately
retain OS error paths if initialization/capture fails again. Freeze this repair
and passing preflight tests before the distinct four-slot attempt. No changes to
qualification gates or application status. No initial timing exists to compare.

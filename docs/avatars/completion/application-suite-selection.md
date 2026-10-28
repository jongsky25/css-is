# Application suite and explicit avatar opt-ins

`python -m pytest --application-suite` collects the complete application suite
while leaving 41 explicitly disabled avatar experiment modules uncollected.
The exact module/env/value registry is `tests/avatar_opt_in_suites.py`; every
entry already declares its own module-level opt-in guard. Collection produced
7,061 tests across 393 modules. Offline analysis unit tests stay included.
Default `pytest` is unchanged and can still collect those opt-in modules.
When a module's documented opt-in is enabled, application-suite mode includes it;
a collection check with CSS_AVATAR_BASELINE=1 includes all three customizer tests.

This avoids starting archived GC/native experiments merely to satisfy normal CI.
The zero-failure/zero-skip JUnit gate is unchanged. Current avatar regressions,
all eight animal rigs/care cases, customizer/seasonal behavior, visibility/touch,
and performance checks execute explicitly in the dedicated avatar workflow.
No failed result is relabelled or dropped; prior Frida collection failures and
superseded hosted artifacts remain recorded. No performance gate is waived.

The mixed CPU-profile unit module contains one executable Yappi probe as well as
17 inert analysis tests. Application-suite mode explicitly deselects only
`test_python_profiles_thread_started_before_profiler` unless the existing
`CSS_AVATAR_CPU_DIAGNOSTIC=1` opt-in is set. This is reported as a deselection,
not a skipped or passing test. The 17 offline cases still run and pass without
profiling; default pytest behavior remains unchanged. Application collection is
now 7,060 selected tests across 393 modules (one diagnostic case deselected).

# Diagnostic helpers, not application dependencies

`throttle_probe.c` wraps entry/exit around Chromium's original POSIX SIGUSR2
handler. Compile with `gcc -shared -fPIC -O2 throttle_probe.c -ldl -o
/tmp/avatar-throttle-probe.so`. `tests/test_avatar_signal_diagnostic.py` supplies
LD_PRELOAD only to its diagnostic browser and writes native records per PID.
Do not use this probe to subtract time or claim an acceptance pass.

The Docker cpuset experiment was rejected. `launcher.c`, `Dockerfile` and
`run_cpuset.sh` are retained only for reproduction in the original /workspace
UID1000 environment. Build the static launcher in a temporary context with
`gcc -static -O2 launcher.c -o launcher`, then build the scratch image named
`avatar-cpuset-fixture` using the supplied Dockerfile. It reuses the host root
read-only, mounts only workspace/tmp writable, drops groups/GID/UID before exec,
and has no network. It requires the managed local Docker daemon. It is not
portable production infrastructure and is not part of hosted verification.

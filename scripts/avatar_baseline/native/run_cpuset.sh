#!/bin/sh
# Local-only fixture. Reuse exact host binaries read-only; drop to task UID.
# Kernel cpuset prevents browser threads widening affinity; quota has headroom.
set -eu
exec env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH docker --host=unix:///var/run/docker.sock run --rm --network=none --pid=host --cpuset-cpus=0,1 --cpus=3 -e HOME -e CSS_TEST_NOW -e CSS_AVATAR_BASELINE -e CSS_AVATAR_MATURE -e CSS_AVATAR_CPU_DIAGNOSTIC -e CSS_AVATAR_CPU_RUNS -e CSS_AVATAR_OUT --mount type=bind,src=/,dst=/host,readonly --mount type=bind,src=/workspace,dst=/host/workspace --mount type=bind,src=/tmp,dst=/host/tmp avatar-cpuset-fixture "$@"

# CPU isolation capability inventory — no new performance run

Use a single read-only snapshot of current guest topology, known cgroup CPU/cpuset
files and current-user writability, process affinity, cgroup membership and scoped
mount metadata. Preserve exact script/commit identity. No privilege escalation,
control writes, arbitrary process/environment discovery, host load sampling loop,
benchmark, CPU reservation claim or qualification run. Guest cpuset/affinity alone
cannot prove virtual-host CPU exclusivity.

Inspect the connected runtime status and discover only its available control tools.
Retain the safe selected status fields and exact tool capability descriptions;
exclude credentials, unrelated network details and provider logs. Inspect existing
repository workflow runner labels. A read-only GitHub runner inventory may be
attempted; if denied, preserve the denial and do not infer that no runners exist.
No network-policy bypass or new paid infrastructure. Freeze before local inventory.

If no supported isolation/reservation control or documented isolated runner is
available, record a hard infrastructure blocker and the exact handoff requirements.
Do not replace it with taskset, nicer scheduling, a fresh container, a quiet window,
large unverified CI labels, provider attestations invented by the agent, or a
repeat of failed qualification. All prior acceptance and gates stand unchanged.

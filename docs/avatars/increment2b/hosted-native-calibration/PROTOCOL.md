# Frozen native-recorder calibration on the GitHub runner condition

User explicitly requests the next calibration after the standard-hosted control
workflow succeeds. Run a separate native workflow, not an app comparison. Standard
ubuntu-24.04, verified immutable Python 3.12.14 trixie image, Chromium
156.0.8078.47 / ELF 1c5dca8527a61d07372e489142bee26af1bcaf71, locked Playwright
1.62.0 and Frida 17.5.1. Preserve actual host CPU/resource and GitHub provenance.

The isolated job container explicitly adds only SYS_PTRACE so Frida may inspect
its own synthetic Chromium renderer; no host PID namespace or privileged mode.
Record and require this capability before proofs. No resource/quota/affinity
change, host-load admission, network-policy bypass or paid runner. Read-only repo
permissions and no app secrets. Same immutable Python image as the successful
control diagnostic. New condition is explicit, not proof of physical isolation.

Sequential gating: fresh native selftest on this host (20 clock brackets, four
threads, 1024 immutable records, exact 32/36 overflow), independently re-audit;
then fresh exact live DOM/SVG/style receiver proof (384 pairs/null returns and
unchanged fixtures), independently re-audit. Exact native agent source continuity
must hold. Any prerequisite failure stops before the four-slot calibration.
Retain all proof raw outputs, including failures; never replay an unchanged
failing prerequisite to obtain a favorable result.

After both proofs pass, existing frozen lifecycle v12 machinery runs exactly four
fresh control/probe/probe/control slots, retaining nonzero exits and every capture.
Original 12 mixed 3000-element documents, 32 receivers per group, selector caching,
navigation arming, measured clocks, natural collection and complete trace. No added
per-phase CPU sampling in this qualification window: only declared existing observer
work and the outer inventory before proofs. No forced GC, cache flush, sample
reduction, exclusive ownership byte claim or omitted observer costs. Control-only
diagnostic v2 deadline helper is not active in ordinary lifecycle v12.

Require unchanged <=5% and <=250ms observation gates, <=20% control variation,
<=1.20 paired durations; immutable exact clock/phase/thread/ABI/canary/overflow and
no pending/dropped native records; all 1536 receiver joins and source-labelled
reclamation for DOM/SVG/style in BOTH probes, with natural MajorGC and native sweeps.
Archive and independently reproduce the complete audit and native-period summary.
Only a complete pass qualifies this instrument for a separately frozen application
calibration. Application qualification and 2B acceptance remain false in all cases.
No app comparison, candidate promotion, merge, deployment or later increment follows.

Freeze source/tests/policy first, then pin that exact SHA in a separate workflow
added to setup PR #511. Its path-limited PR event performs one prescribed attempt.
Keep the prior successful control workflow unchanged. Artifact upload on failure
and a phone-readable summary must expose raw failures, not convert them to success.

# Uninjected GC comparison from a phone

Open GitHub Actions → Avatar uninjected GC comparison. The setup pull request
starts one fixed four-slot comparison on hosted Linux x64. No laptop, SSH or
upload is required. Read the summary and avatar-uninjected-gc artifact.

Order: counter only / GC trace only / GC trace only / counter only. The same
workload runs in every slot. Frida attachment is forbidden and the job drops
SYS_PTRACE. It adds no heap snapshot, collection request or workload wait.

Every result and failure remains retained. This diagnoses measurement conditions;
it cannot qualify the native observer, accept memory or deploy the product.
No automatic retry or product change follows. The manual button still requires
default-branch registration under the repository's existing release policy.

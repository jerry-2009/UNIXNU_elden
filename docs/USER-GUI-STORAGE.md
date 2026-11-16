# User GUI trial and Data exhaustion — 2026-11-16

The user-operated v156 session used the already-qualified image
`5f8837128ab71b2bc6d2b45c02f9133aa30b5a2243663ce425bda859588d29df`
with a6GiB XNU memory window and a512MiB sparse RAM Data seed. The host allowed
an approximately8-minute session, then performed typed return and complete
stock restoration. Root/green and original charging/radio/scan settings remained.

The user reported SpringBoard crashing/reloading, slideshow-like animations and
Settings→General→About showing Capacity1GB, Available9.9MB. These labels describe
storage, not RAM; the precise rounding/display convention for1GB has not been
verified. They are not evidence that XNU has only1GB of memory.

The raw log contains repeated APFS `ENOSPC` on disk1s1, including SpringBoard,
iconservicesagent, logd, triald and other daemons. Some deletion transactions also
failed for lack of metadata/reserve space. Data exhaustion is therefore proven;
the exact SpringBoard exit reason and whether space exhaustion is its sole cause
are not proven. The capture reports975 dropped bytes, so missing exit/pressure
lines must not be treated as absence of those events.

SMP hold records remained `online=ff` throughout their reported window. The two
frequency domains were sampled at1996.8MHz/1017.6MHz in the early CPU survey.
This is neither proof of maximum frequency nor a reason to force all cores busy.
The early32 full-frame CPU copies took122.7–140.3ms, median138.3ms at the recorded
19.2MHz counter frequency. Those capped samples are not a continuous GUI FPS
measurement. Both software display cost and Data failures need attention.

Next prepare a separately qualified2GiB sparse Data seed, preserving the original
logical files, UUID, anonymous raw inode ownership and APFS checks. Its native
staging/recovery guards and packer must be explicitly adapted and checked before
use; merely changing the image size is not a flashable candidate. Sparse pages
are allocated on writes, but resident-memory growth still needs runtime testing.
Persistent writable Data remains a separate unfinished requirement; the existing
128GiB root bundle is not automatically used as application Data.

Continue mainline Wi-Fi work alongside this demonstrated GUI blocker. Keep
`codex/elden-gpu-offline` separate. The reviewed `offline-peripheral-fixes`
STATUS at commit0331cda establishes pen/haptics/RTC/sensors/camera scope but says
implementations/validation pending and nothing merge-ready. No component was
copied or integrated. Uncalibrated motor output and physical speakers stay off.

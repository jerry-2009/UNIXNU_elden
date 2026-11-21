# Load-aware SCMI governor component

The original v147 component was validated offline; [v148](../../profiles/cpu-governor/README.md)
has since completed a bounded native/hardware trial. It did not establish a
power saving. The generated policy header is now scoped as EldenCpuFreqPolicy.h
to avoid the existing power-header name; original v147 reproduction uses e6dd6cd.

The demand policy and transaction controller target arm64/iPadOS17. This page
documents their design and original component tests; the v148 profile records
the later real transitions and Android restoration. Component tests alone do
not establish power savings, thermal behavior or charging success.

## Reused policy

`upstream/source.json` fixes Pagani-Drivers commit
`c888efd3ce1b817d13f28783a77cf689cb2255c9`, preserving the original governor file
and BSD-2-Clause-Patent license byte-for-byte. Its README reports real SM8750
frequency-control observations; its separate PSCI idle code is explicitly
untested and is not imported. Sheng's load-based governor supplies the same
principle; SM8550 EPSS registers are not used on Elden.

`GovernorSource.py` extracts the original arithmetic/CPU-load section through
`cpuWindows`, changing only the include name and adding the namespace/header
closure. No upstream policy function body changes. It excludes the upstream
Control/retry/I/O layer. The policy retains20ms windows, per-CPU eight-window
frequency-weighted demand, busiest-CPU selection,1.25 headroom, burst response,
three-of-four-window down hysteresis and250ms touch hold.

The controller clamps policy ceilings to explicitly configured, firmware-listed
levels at or below the sustained frequency. With `Config::bootCeiling=true`, each
ceiling is also clamped to its initial exact LEVEL_GET result; floors and touch
targets are clamped too. This is the intended first hardware setting, limiting
NCC0 to the observed boot level and leaving the already-low NCC1 ceiling intact.
It is a bring-up bound, not the final usable-frequency policy. Higher ceilings
require separate on-device thermal/frequency qualification. No GPU, screen-state
or app-launch data is fabricated: those optional policy inputs remain disabled.

## Transaction and recovery contract

- A sole runtime worker owns a zeroed Control and the existing CPUCP lease. It
  supplies real eight-core load windows, fresh readiness and a touch counter.
  Missing readiness/interrupt-context callback, bad capability/table/cap or an
  inexact initial level prevents the controller from issuing any SET.
- `PERF_LEVEL_SET` is admitted only during one checked request; LIMITS_SET always
  remains denied. At most one transition is pending across both domains. The
  firmware's rate limit is preserved, with alternating domain priority.
- A SET ACK is not completion. The controller waits at least20ms, then reads the
  actual reported level within a1-second bound. Only an exact, timely response
  commits the governor's new level. Pending transitions do not feed guessed
  frequencies into demand history. No experimental SET is replayed.
- Stop/readiness loss/invalid load windows end normal requests. Where transport
  and transition state remain known, each changed domain gets at most one
  original-level restore request and must return that exact level.
- A missing/malformed reply, uncertain SET, expired transition, failed restore
  or reversed clock ends in `Held`. No subsequent I/O is issued and no successful
  restoration is claimed. The native wrapper must retain the uncertain lease
  and continue the qualified reset fallback; it must not forcibly clear a busy
  mailbox. A completed explicit SET rejection can restore earlier known changes;
  SCMI COMMS/GENERIC/HARDWARE/PROTOCOL error replies are treated as uncertain,
  rather than proof that no clock change happened.

`terminal()` means the worker has no more actions: **Held and Refused are also
terminal**. The worker must publish its final phase/restore result using release
ordering; the recovery hook reads that completion with acquire ordering. It must
not read the mutable, non-atomic Control concurrently. Its success test is a
published `phase == Stopped` and the restore outcome, not terminal alone. Refused-before-SET still does
not prove an interrupted probe left the mailbox free. Mapping/lease release needs
the existing channel-status check.

## Validation and reproduction

`tools/test_cpu_governor.py --cxx /usr/bin/clang++ --output NEW_DIR` executes the
actual extracted policy, controller and frozen SCMI transfer code with a fake
firmware.162 scenarios/221812 checks passed under ASan/UBSan, covering128 varying
workload traces, forbidden writes with zero I/O, delayed ACK-vs-OPP completion,
late confirmation, explicit rejection, transport loss, both-domain restoration,
rate limits, stop during a transition, invalid load-domain/table inputs and clock
loss. The check count includes low-level register/packet assertions, not distinct
scenarios. This is firmware modeling, not hardware or concurrency testing.

`tools/build_cpu_governor.py --llvm LLVM_DIR --reference-native NATIVE_MACHO
--output NEW_DIR` compiles `GovernorApi.cpp` as a freestanding scalar object.
It has five explicit exports, no unresolved imports, no automatic initialization,
no FP/SIMD or PSCI instructions, and zero compiler warnings. The final object is
`0b895000dfec9f72351aa489cfd0bf6d9b354e1f982af5c8ef9321ba577f8781`;
exact inputs and test results are in [validation.json](governor-validation.json).
The generated policy SHA256 is
`c78ae7b5a0080a76c3a1727fd067c56ebb77bc1387baef0e1f609e53661191d3`.

The next integration must preserve the frozen observer modes and bind a new
explicit mode to the current GUI/PD kernel, real input/counter APIs and fresh
battery/PD/recovery gates. Add the CPU stop request **before** radio/backlight/PD
shutdown in the qualified recovery path. The callback posts an atomic request
and waits boundedly for its worker; it never drives this controller concurrently.
Verify both source/ABI binding and the independent watchdog budget, then run one
frequency/load/power/restore trial. Do not flash this standalone object or reuse
the current v146 boot hash as if it contained the governor.

Evidence: workbench `lab/records/cpu-governor-v147-20261115` and
`edl_work/cpu-governor-v147-20261115`; Mac isolated
`cpu-governor-host-v147-final3` and `cpu-governor-native-v147-final`.

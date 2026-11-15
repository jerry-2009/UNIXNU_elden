# CPU load and firmware-level observation

This extends the frozen `CpuPerfSurvey.cpp` through a SHA-bound transform. Mode1
keeps the original survey. Opt-in `elden-cpu-survey=2` (or `ecp=2`, with the long
name taking precedence) waits for recovery, root/Data/PID1, confirmed current PD
state and all eight running CPU records. It then waits30 seconds and captures
nine points: eight3-second CPU-load intervals, alongside two SCMI level queries.
No PERF_LEVEL_SET, LIMITS_SET, PSCI suspend, voltage or charger operation is added.

The purpose is to distinguish sustained CPU work from idle time at firmware-left
performance levels before implementing DVFS. This is not itself a power-saving
driver or proof that CPU load causes the current net-discharge result.

## Sources and boundaries

- Sheng `5ae8b4876a378a5104330a5ae514ec9d6deae373`:
  `package/CpuFreqProbe.cpp` and `zzye-sheng-cpu-idle.patch` use real XNU idle
  accounting for governor demand. Its SM8550 EPSS registers are not copied.
- Pagani-Drivers `c888efd3ce1b817d13f28783a77cf689cb2255c9`:
  `PaganiArmCpu/ArmCpu.cpp::cpufreqSample` uses PROCESSOR_BASIC_INFO/CPU_LOAD_INFO. Its README
  describes measured SCMI frequency control, while **PSCI idle is explicitly not
  hardware tested**. No idle-state or highest-frequency policy is enabled here.
- ArmadaOS TB322FC lineage → h0cheung
  `6f97250ead155fc3b980856323e99a4623dae73d`: SM8750 CPU0–5/NCC0 and CPU6–7/NCC1,
  CPUCP TX0/shared-memory layout. No TB321FU/SM8650 input.
- The actual reconstructed Darwin23 `processor.c` uses recount and divides each
  USER/SYSTEM/IDLE time by `hz_tick_interval`; NICE is zero. Readback timestamps
  and all four raw counters are logged. Modular32-bit deltas allow natural wrap,
  while reset/missing/offline/implausible intervals are rejected. Independent
  rounding permits three ticks, and only intervals of at least50 ticks and at
  most10 seconds qualify. Kernel exports are reused; no new core helper.

A completed explicit SCMI status−1/−2/−3 disables queries for that domain and
marks the whole observation incomplete. It does not identify the reason for a
domain's refusal. Transport, malformed or unknown-level errors stop all queries.
An unresolved transfer retains the original mapping/owner lease. PD loss stops
sampling; no retries or forced mailbox clearing are introduced.

`table-khz` is the firmware-reported performance level mapped through its table,
not an independent measurement of instantaneous clock frequency. CPU utilization
is an interval average; eight registered/running CPUs do not imply100% load.

## Reproduce

`tools/test_cpu_power_observation.py --cxx /usr/bin/clang++ --output NEW_DIR`
executes the actual observer body against deterministic kernel/SCMI fixtures and
ASan/UBSan. `--parser-source PATH/pexpert/gen/bootargs.c` additionally runs the
SHA-pinned actual XNU parser, including the combined1023-byte menu. Native builds
use `tools/build_charge_verification.py --cpu-power-observation` with the existing
clean-build/parent-build/original-kernelcache/llvm/output inputs; parent must be
the qualified `pd-power-trial` kernel. Only CpuPerfSurvey is rebuilt.

For a full clean build, add `--cpu-power-observation` to the existing native17
charging option chain, omitting `--pd-gui`. Required PD/backlight/window stages
are selected automatically; the new profile uses normal `ebl=6`, not dimming.
The complete stages have run separately; the newest combined empty-directory
command has not been repeated. Original frozen profiles remain unchanged.

`tools/analysis/assess_cpu_power.py RUN --output NEW.json` checks capture/image/
session identity, recomputes loads from raw counters, and retains partial-domain
failures and character losses. See `profiles/cpu-power-observation` for the actual
candidate and hardware result. No upstream update automatically replaces inputs.

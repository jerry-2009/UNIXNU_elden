# Governor runtime integration — 2026-11-15

Current result: [v148](../../profiles/cpu-governor/README.md) completed native
integration and one bounded hardware lifecycle after maintenance ended. Active
RPC interruption and power savings remain unaccepted; current evidence is in
that profile.

The mode3 worker and recovery transformation passed16 ASan/UBSan host scenarios,
then native linking, packaging and the bounded v148 trial. Initial Windows/WSL
work respected the other task's macOS maintenance marker; Mac/device work began
only after that task archived the marker. The older v146 image is preserved.

`RuntimeSource.py` derives from the exact v146 observer SHA253d6075, leaving the
mode1/2 source bodies and their query-only message callback intact. Explicit
`elden-cpu-survey=3`/`ecp=3` dispatches the governor worker. The explicit
[build/pack/audit route](../../profiles/cpu-governor/README.md) includes source-routing
tests, the verified native contract and hardware evidence.

## Runtime behavior

- Wait at most240 seconds for recovery/RAM Data/PID1, current PD Ready, all eight
  running processor records, and at least180 seconds of recovery deadline.
  The existing charge-policy readiness requires a fresh complete poll, battery
  present/healthy,3500–4500mV, temperature5–42°C and input online. The existing
  locked temperature getter adds a5–40°C gate and pins the transport epoch.
- Observe a30-second no-SET baseline, acquire the existing CPUCP lease and map
  only the established TX/shared-memory ranges. Use the actual19.2MHz timebase,
  actual XNU tick interval, unchanged SCMI accessors and an interrupt-context gate.
- Run at most90 seconds with20ms sampling. Validate raw tick deltas for reset,
  time reversal, gaps, offline CPUs and domain mapping; then feed unchanged
  upstream cpuWindows/governor arithmetic. Touch activity comes from completed
  even values of the producer's atomic native_touch_seq, including release;
  it is activity, not a new physical-touch acceptance claim.
- Keep the initial readback ceiling and declared sustained caps. A set is
  permitted only by the controller, with normal sets withdrawn after a stop
  request. Restoration requests remain possible through the sole worker.
- Stop/readiness loss/epoch change/invalid load window ends normal control. The
  worker restores original levels when state is known. Unknown state keeps the
  mapping and owner, performs no final status read, and publishes Held.
- A release-store publishes only clean/held completion. The five-second recovery
  callback posts an atomic stop request and waits for that result; it never reads
  mutable Control state or executes SCMI. Its timeout remains a failed stop, not
  an implicit successful restore. Scheduler starvation and real watchdog budget
  still require native/hardware validation.

The log distinguishes governor result/error from cleanup result. A clean callback
after a refused/no-write start is not evidence that DVFS ran. Hardware acceptance
must require actual transitions/GET confirmations and inspect the failure fields.
The baseline may overlap GUI startup; do not call that a strict steady-load A/B
without the corresponding frame and workload evidence.

## Correct recovery source

The current-build ShengUfs job consumes NativeUfs.cpp and overrides both virtual
EldenSdamRecovery.inc spellings with
`profiles/v97-wcn/EldenSdamRecovery.inc`, SHAce63730b. It already contains WCN stop.
The base native capture still contains the older v91 SHA46b13297; using that base
header for the new UFS object would lose existing recovery behavior.

The new transformation checks ce63730b, adds the CPU weak hook immediately before
WCN/backlight/PD shutdown, and preserves every prior byte after removing that exact
addition. Its SHA is
`3db3456277d362281f702a0c3d0dd3340fb87e82bd4a095d9d66c9b4dc76c088`.
No UFS transfer, DMA, root extent, write permission or SPMI restart code is changed.

The builder uses the current-units ShengUfs command/closed VFS and
the CpuPerfSurvey command to compile both affected objects, binding only the new
headers/source. It preserves the UFS initializer and all other archive/core members,
checks the new stop provider/consumer and full native/prelink/Apple30/entry/AVB,
then qualifies a distinct candidate. Do not use an old object as a build prerequisite or
overwrite current-build's frozen source manifest to make the delta pass.

## Host evidence

`tools/test_cpu_governor_runtime.py --cxx clang++ --output NEW_DIR` executes the
actual Runtime.inc and stop callback with the real v147 controller/SCMI functions
and modeled kernel/FW access.16 cases/2754 checks cover normal control/restore,
unavailable PD/charge/temperature, owner refusal, mapping failure, early/mid-run
stop, epoch loss, invalid sampling, uncertain SET, stop-before-start and a bounded
callback timeout. It also checks recovery ordering and byte preservation.

Final WSL run used a non-PIE ASan/UBSan executable. A previous PIE executable
exited with SIGSEGV and empty diagnostics; the same binary completed under GDB.
Those records remain in Temp; the cause is not claimed as a driver defect or a
proven WSL defect. The final normal sanitizer run, not GDB, is the acceptance run.
Host models do not prove the native ABI, concurrent scheduling or electrical use.

Evidence is in workbench `lab/records/cpu-runtime-20261115`; one-off generated
files are under Windows Temp `y700-cpu-runtime-20261115`. The complete peripheral
Goal and charging/net-power acceptance remain open. The next subsystem after this
CPU closure is storage, following docs/PLAN.md and the organization reuse audit.

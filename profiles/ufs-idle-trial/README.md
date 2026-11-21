# v156: automatic UFS idle power state

The UFS controller now enters hardware Hibern8 after the stock5000us idle timer,
wakes for reads, and restores the previous XNU controller configuration before
filesystem shutdown. The complete kernel, boot audit and one hardware trial
passed. This closes a UFS power-management gap; **complete charging, battery
endurance and whole-system sleep are not claimed**.

## Why this change

The existing bring-up code disabled AHIT to keep the link awake across its initial
state query/first transfer, then never restored automatic idling. Original Android
on this TB322FC reports `auto_hibern8=5000`, clock gating/scaling enabled and
growing hardware enter/exit counters. ArmadaOS's exact SM8750 source
`6f97250ead155fc3b980856323e99a4623dae73d` supplies the UFSHCI AHIT layout,
AH8 capability, Qcom internal clock-request mask and Hibern8 counter registers.

The trial uses the **board's observed5000us**, not Linux's generic150ms default.
Source hashes and Android reads are in [source evidence](source-evidence.json).
No charger/FET/OTG, external clock-rate or SMMU routing write is introduced.

## Hardware evidence

- Controller CAP `d5c7031f`, version `60010000`, inherited SYS1 cycles/us403;
  inherited AHIT0 and AH8_CFG1800. No frequency was programmed or measured.
- AHIT `5f4` (500×10us), AH8_CFG183c and IE61 read back after enabling.
- OS and SystemOS each completed16 idle/read cycles. Every20ms idle interval
  produced a hardware enter and exit, and each4KiB/128KiB read passed the existing
  protected block hash. Total32 enters and32 exits; root remained disk5s1.
- Reads after idling took roughly0.8–1.0ms. This is a latency cost of the tested
  policy, not a throughput improvement or an independently timed5ms transition.
- Before reset, stop returned0 / phase Restored / error0 / active0. The
  controller transaction verified AHIT0, IE1, active link and the original owned
  AH8_CFG bits before the existing IRQ withdrawal and filesystem shutdown.
- SMP admission and software Home reached the existing desktop; white widgets
  remain. No physical input or system suspend/resume acceptance is implied.
- Session-bound sync/reset, physical fastboot and complete stock SHA restoration
  passed. Android/root/green/boot completion and original charging settings were
  confirmed. Android UFS returned to5000us with clock gating/scaling1 and PM levels3.

Capture3702114B/drop1172, no reconnect. All32 critical rows/counter deltas and the
restoration record were retained, but the whole log is incomplete. Tail10 received
high-SOC current samples had median0mA, including positive/negative samples;
workload, SOC and capture loss prevent any net-charging or energy-saving claim.

Image SHA256: `5f8837128ab71b2bc6d2b45c02f9133aa30b5a2243663ce425bda859588d29df`

Session `410a995d2346b0d3`; rollback1738713600/footer0/parent3 unchanged.
All build/host/device jobs ended; Android sleep was requested.

## Implementation and failure handling

`IdleSource.py` layers over the verified owned-DMA queue source, removing v155's
diagnostic QD batches. `Ah8Control.h` admits only the owned empty legacy queue,
AH8-capable Qcom3+ controller and valid inherited timer configuration. Register
writes and readbacks run under the existing host mutex. The only additional
configuration writes are AHIT0x18, its error interrupt bits0x60 in IE0x24 and the
documented clock-request bits0x3c in Qcom AH8_CFG0xfc; unrelated bits are preserved.

Unexpected Hibern8 enter/exit interrupts become fatal only while automatic AH8
is armed. Both IRQ and polling paths retain the current DMA quarantine behavior.
Shutdown disables the timer and restores IE before manual UIC wake, then restores
owned clock-request bits. It never cancels/resets a command or pretends that a
failed/busy restoration succeeded. No new SoC sleep or PHY power-off path is used.

87 actual-controller ASan/UBSan cases cover admission, ordering, readback failures,
busy restoration, failed wake and unrelated-bit preservation.20 actual generated
queue/IRQ cases cover the active-AH8 error mask while preserving manual-UIC
semantics.10 real-capture mutations reject missing/bad counters, data failures
and unproven restoration. Hardware, page tables and OS scheduling are modeled
in host tests, separately from the hardware evidence above.

One UFS object changes. Other archive/core members, original initializers,
scalar code, entry and30 original Apple execution ranges are preserved. Existing
warnings remain recorded. [Validation](validation.json) binds sources and builds;
[hardware](hardware.json) retains the readings and limitations.

## Reproduce and continue

```sh
python3 tools/build_clean.py --variant bluetooth --bt-exit-stack \
  --software-keystore --bluetool-launch --bt-transport-trace \
  --bluetool-lifecycle --bt-registry --bt-helper-trace --bt-process-lifetime \
  --bt-address17 --ufs-idle-trial --inputs inputs.json --output NEW --target boot --jobs 4
```

This builds all prerequisites and records the idle option in resume identity.
The newest combined empty-directory command has not been rerun; individual
native/entry/packing/audit stages have run. Staged builds use
`build_charge_verification.py --ufs-idle-trial` over v155. No old v99 binary is
required. Mac final: isolated/ufs-idle-v156. Workbench: edl_work/ufs-idle-v156-20261115,
edl_work/live-ufs-idle-v156-20261115 and lab/records/ufs-idle-v156-20261115.

Further power acceptance needs representative SOC/workload, full charge-window
crossing/recharge and persistence. Keep the original input budget/thermal
protections and avoid repeating high-SOC hold or rejected DC writes. Evaluate
the5ms wake-latency tradeoff before calling it the daily optimum; retain this
qualified feature without repeating its diagnostic reads in unrelated trials.

# WCN shared supply owner — offline component, 2026-11-15

Follow-up: the [native WLAN adapter](WLAN-POWER-NATIVE.md) now compiles and
uses this provider, including atomic live-lease queries. It is not yet integrated
into a whole kernel or tested on hardware. The330-case record below describes
the initial core version; follow the linked report for the current335-case build.

Wi-Fi must not acquire a Bluetooth lease or require Bluetooth firmware to be
running. `WcnSharedPower.h` now defines two independent consumer leases over one
platform-lifetime supply/PDC executor. This is **host-tested and ARM64/iOS17
compiled, not connected to the native worker or tested on hardware**.

## Source and behavior

The physical sequence follows ArmadaOS's TB322FC source chain to h0cheung
`6f97250ead155fc3b980856323e99a4623dae73d`,
`drivers/power/sequencing/pwrseq-qcom-wcn.c`: shared regulator dependencies,
WCN7861 BT reset50ms/WLAN-off100ms/BT-off100ms, WLAN enable and both targets'
post-enable50ms. WCN7861 does not specify an inter-GPIO delay. These are SM8750
board inputs, not TB321FU/SM8650 or Sheng register values.

The controller resides in the existing `WcnPower.c` translation unit through
`WcnSharedPower.inc`. It reuses the six physical rail definitions, initial PDC
messages, voltage qualification, PLL decoder, OL-CPR arithmetic/aliases and
command formatter. There is no second physical supply provider or fake
`pwrseq_qcom_wcn_set_ol_cpr` success symbol.

- The first consumer qualifies both GPIOs as off, then prepares shared supplies.
  An unknown live boot consumer is refused without any write or adoption.
- Joining/restarting a consumer does not repeat initial PDC/rail votes or reset
  the other radio. The requested radio alone receives its documented sequence.
- Full transactions, including CPR, use one nonblocking atomic admission gate.
  Reentry/contention returns `-11` without I/O; callers must not spin in IRQ or
  panic context. This component has no worker, timer or autonomous retry.
- Firmware requests merge wake/sleep maxima across the two consumers. Partial
  requests retain omitted fields. New votes commit only after all real QMP calls
  succeed. A later low request cannot undercut the peer's vote.
- Stop lowers only that consumer's reset and retains shared baseline/PDC votes,
  even when both known consumers stop. Unregistered boot consumers prevent a
  qualified whole-rail power-off decision. This is not deep-sleep support.
- Epochs strictly increase separately for BT and WLAN. Stale callbacks fail;
  snapshot reads use the same gate. Partial/uncertain transactions enter terminal
  `Held`; maps and vote records must survive until platform reset. Snapshot lease
  bits alone do not imply readiness when `held` is true.

The old `EldenWcnPower` layout, public signatures and callback order remain.
Only rail qualification and CPR sending were factored into private helpers.
Legacy entry points and the new owner must **not run simultaneously** against
the same hardware. Frozen profiles retain their original source versions/hashes.

## Validation and reproduction

From a clone on Windows with Ubuntu WSL:

```powershell
py -3.12 tools/test_wcn_shared_power.py --wsl-distro Ubuntu --output C:/Users/Public/wcn-owner-test
py -3.12 tools/test_wcn_cpr_compatibility.py --wsl-distro Ubuntu --output C:/Users/Public/wcn-compat-test
```

Use a new output directory each time. The first command compares actual old/new
legacy functions at commit `2062ad1` across130 fault positions, then exercises
both consumer orders, partial CPR updates, all8 command-error positions,
GPIO/readback/timing faults, stale epochs, reentry and concurrent admission.
Final result: **330 scenarios /50658 checks**, ASan/UBSan passed. Physical
callbacks are recorders, not MMIO. The older compatibility suite additionally
passes4096 comparisons/all8 command failures and12 scenarios/344 assertions.

On macOS with Xcode/iPhoneOS SDK and LLVM:

```sh
python3 tools/build_shared_wcn_cpr.py --llvm /path/to/llvm/bin --output /new/path/wcn-owner-native
```

One `libEldenWcnPower.a` and `OlCprPlan.o` compile with warnings as errors,
no FP/SIMD or automatic initializer. WcnPower exports the original12 symbols
plus4 owner APIs; remaining imports are `strcmp` and `bzero`. WcnPower object
SHA256: `30f0198179389859da6d8ee719e81f5ea2245739ab3360a59a8fb2a3b8459215`.
This does not constitute full kernel linking, an image or radio acceptance.

Evidence: [structured record](evidence/wcn-shared-power-20261115.json).
Workbench logs: `lab/records/wcn-shared-power-20261115`, native output:
`edl_work/wcn-shared-power-20261115/native1`. Mac isolated component build:
`lab/wcn-shared-power-20261115/native1`. The initial188-case result is superseded
by the expanded suite. Its first expanded run failed a test's fixed command-index
assertion after adding partial updates; the final test checks the full merged
four-command result. Failed output is preserved, not reported as a driver fault.

## Required native integration

`WcnPowerNative.cpp` currently creates a BT worker-owned Context and retains its
maps after completion. It does not yet expose WLAN ownership. Next integration
must put the new owner and mappings under platform lifetime, bind the exact
TB322FC PCI110e device and WLAN epoch, and let BT-off WLAN startup use the same
real QMP/RPMh/SPMI primitives without BT firmware preparation. WLAN_EN GPIO16
needs a source-qualified TLMM writer/readback; the current native `wlan_get`
only reads it. Both native consumers must migrate together with real stop/RPC
handling. No old Bluetooth lease may authorize WLAN CPR.

The exact Linux QMI adapter must convert its real PMU parameters and return the
owner's result. PCIe/BAR/MSI/DMA/MHI/QRTR and network callbacks remain separate
requirements. Only after complete source-only rebuild and recovery verification
should a bounded hardware trial start. Existing v156/stock images are unchanged.

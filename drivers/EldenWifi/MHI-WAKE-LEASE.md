# Bounded MHI wake-reference contrast

This diagnostic candidate tests whether a device power transition prevents
later WMI commands from being consumed. The previous trial reaches station4
but CE3 stops after the initialization command completions; later WMI commands
remain unreaped and credits reach0. That does not prove a power-state cause.

The exact TB322FC/Armada Linux PCI path already uses
`mhi_device_get_sync()` and `mhi_device_put()` to keep MHI awake during BAR
access. The contrast uses those actual compiled MHI functions and holds one
reference from the real Peach PCI start until ordinary stop or power-down.
A failed get propagates its error and owns no put. The existing timeout,
credit, command/descriptor, IRQ and firmware behavior are preserved.

Only a separately compiled and qualified `--mhi-hold` worker/runtime pair
enables this behavior. The native admission uses the existing `ewt=1` owned
runtime option; no boot argument or recovery feature is removed from the
already full1023-byte menu. The ordinary build excludes the hook and continues
to use the previous PCI implementation. This candidate remains an experiment,
not a daily-use power policy; a persistent wake reference can increase power.
The existing bounded automatic return limits the experiment.

`MhiLease.inc` is the actual helper. `peach/MhiLeasePatch.py` inserts get/put
calls only at the real PCI lifecycle boundaries, and verifies the insertion
can be reversed to the exact plain input. Host tests execute34 helper cases
with ASan/UBSan: disabled option, absent/wrong device, failed get, same/foreign
owner, duplicate start/stop and balanced release. MHI state is modeled there.

The actual PCI object compiles for arm64/iOS17 with120 inherited warnings.
Its new MHI get/put imports resolve to actual runtime definitions; only the
native opt-in hook is a new external provider. The full125-object binding
retains the current MAC/PHY stride fix, CE/MHI/IRQ/firmware objects and124
objects from its immediate parent. Native worker, full kernel, prelink,
12profile mutations, entry and signed package pass. Core/30original Apple
execution regions/entry7124 are preserved, floor1738713600/footer0/parent3.
Package1 refused the oversized extra argument before signing; package2 keeps
all inherited argument bytes and is the accepted candidate.

```sh
.venv/bin/python -B tools/test_wifi_mhi_lease.py \
  --cc /path/to/clang --output out/mhi-lease-host
.venv/bin/python -B tools/build_wifi_mhi_lease.py \
  --runtime-build /path/to/source-built-runtime \
  --stride-build /path/to/qualified-stride-runtime \
  --llvm /path/to/llvm/bin --output out/mhi-lease-runtime
```

Then use `build_wifi_net17_native.py --mhi-hold` and pass that runtime with
`build_wifi_net17_kernel.py --mac-phy-runtime out/mhi-lease-runtime`. The
qualified pair is mandatory; mixed or altered pairs are refused. Build inputs
and full component/package records are in
[evidence](../../docs/evidence/wifi-mhi-lease-20261120.json).

The live decision must distinguish successful get and retained release,
WMI timeout/credit completion, scan/BSS, and the full native stop/physical
fastboot/stock Android restoration. A wake reference alone is not networking
acceptance. Do not invent credits, extend wait budgets or skip firmware checks
to make this contrast pass.

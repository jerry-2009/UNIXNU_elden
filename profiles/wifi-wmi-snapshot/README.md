# v178 first-WMI-failure snapshot

This profile retains the v177 service/scan gates and adds a single observation
at the first WMI timeout. The new observer does not acknowledge IRQs, pump work,
change masks, extend a timeout or change any firmware/clock/power setting.

`IrqSnapshot.inc` is appended to the exact frozen `lx_rt.c`. It reports the
registered/enabled/pending/strict/disabled/running vector masks plus dispatcher
depth, active callbacks, held mutex count and polling mode. It traverses only
the fixed64-slot IRQ table and runs on the wireless worker. The native observer
reads the already-owned MSI status/enable/mask and MHI status after admission,
then prints read errors, native counts/pending/faults, current DAIF/MPIDR and
configured target affinity. These are observations, not a cross-register atomic
snapshot or proof about every CPU's interrupt state.

Build the observer with `tools/build_wifi_irq_snapshot.py`, supplying the
original runtime, qualified v172 platform runtime, original init build, frozen
component repository and LLVM. This recompiles one C unit and reuses124 actual
objects. Supply the result to `build_wifi_service_native.py --control-trace
--service-scan --wmi-snapshot-build <runtime>` and to
`build_wifi_service_kernel.py --irq-snapshot-build <runtime>` using the existing
[service inputs](../wifi-service/README.md). Core/helper/cache/trust are unchanged.

`test_wifi_control_native.py --service-scan --irq-snapshot` passes the existing
seven native/real-queue scenarios, actual IRQ-table pending/disabled/running
states and non-mutating repeated reads, scan gating, ABI and privacy/cap tests
under ASan/UBSan. Kernel socket/MMIO services are not exercised by that host test.
Native compile has1 inherited warning; runtime has32. Native1 failed because the
SDK lacks `strstr`; native2 exposed the two precise new standard-library imports
from the bounded filter. Native3/kernel3 are the accepted outputs. Initial logs
are retained; no failed object was used on the tablet.

## Hardware evidence

At the first timeout: native MSI status0/enableffffffff/mask0, software pending0,
native error0, no in-flight handler, receiver Armed3/count79; logical IRQs
used/enabled1fc0ff, pending0, disabled0, running0, depth1/active1/mutexes3/polling0.
All four register reads succeeded. Current CPU DAIF200 means its IRQ mask is
clear; MPIDR80010100 differs from configured target0, so it is not evidence about
the target CPU's DAIF. MHI status201 is retained as observed.

This does not support a pending interrupt visibly stuck in the host receiver at
that moment. It also does not prove a lost IRQ never occurred, that CE/HTC
processing is correct, or that the firmware returned WMI credits. Next inspect
the first command/credit-report path before changing routing or polling.

Important diagnostic boundary: upstream `nw_wifi.c::wmi_stuck()` subsequently
requests `mhi_force_rddm_mode`. Later repeated failures are not independent
reproductions of the first failure. Its DDR/file comparison uses fixed offsets
from another firmware layout and does not prove Peach RAM corruption. The actual
CE status consumer and hardware producer positions are equal in the capture;
raw `sw_index` uses different bookkeeping and must not alone be called backlog.

ArmadaOS TB322FC6f97250e and Linux7.0.14 have identical HTC C and wifi7 CE C after
line-ending normalization; HTC header differences are copyright/parameter names.
No direct HTC protocol fix was found in that comparison. Other layers still
need diagnosis. Scanner/network acceptance remains absent.

Physical fence/BM-off/sampled-idle/MSI-stop/PERST/WLAN-stop, session-bound reset,
actual fastboot, full stock SHA and Android/root/green/original settings recovery
pass. MHI warm reset stays unverified. Capture296668B/dropmax0, no reconnect or
discontinuity, no counter after disconnect. All jobs terminal.
[Evidence](../../docs/evidence/wifi-wmi-snapshot-v178-20261116.json).

# UMAC and CE3 state loss

The additional boundary trial shows CE3 configuration and UMAC request/state
remain valid after pdev creation, IRQ enable and rfkill configuration. Before
the first PMF command the same registers return zero, with CE3 MISC0x80. This
precedes the later forced RDDM, and does not establish the origin of the loss.
[Actual record](../../docs/evidence/wifi-window-boundaries-hardware-20261120.json).

`PciStateTracePatch.py` is an explicit passive diagnostic over the exact
original-shadow, no-cache-window parent. It installs the already-existing
`lx_mmio_trace` callback only if it is null. The callback records up to32
existing writes to UMAC request, global reset, MHICTRL and selected CE3 R0
registers in RAM. It writes no device register, does not log inside the callback,
and retains every original PCI operation. CE aliases require the actual window
to be0x37. The original final put is recorded before an owned callback restore.

Each existing0x3004 timeline read additionally records raw MHICTRL/MHISTATUS,
software PM/state/EE and both MHI wake-reference counts, at most16 times. The
first request value other than1 dumps the bounded write history. No payload,
command parameter, key, MAC, SSID or firmware bytes are recorded.

This distinguishes writes made through this runtime's callback path from a
device-side state change. It is not a complete inventory of CPU writers, an
atomic snapshot, or proof that no unobserved writer exists. No ring is reinstalled
and no wake, credit, clock, timeout or firmware policy is changed.

17 actual-helper ASan/UBSan scenarios cover retained writes, callback ownership,
overflow, window qualification, read bounds and restoration.49 composition
mutation cases, scalar PCI/full-kernel/30Apple/entry7124/signature checks pass.
PCI inherited warnings remain. These tests model MHI and MMIO; hardware trial
is pending in [candidate evidence](../../docs/evidence/wifi-pci-state-20261120.json).

```text
python tools/test_wifi_pci_state_trace.py --cc CLANG --pci-source QUALIFIED_PCI --output NEW_HOST
python tools/build_wifi_pci_state_trace.py --runtime-build BASE --parent-build WINDOW_PARENT --llvm LLVM --output NEW_RUNTIME
python tools/build_wifi_net17_kernel.py --parent-build SERVICE_KERNEL --worker-build INSPECT_WORKER --net-build NET17 --mac-phy-runtime NEW_RUNTIME --clean-build CLEAN --original-kernelcache APPLE --output NEW_KERNEL
```

Reuse the exact qualified worker and net objects. Package/audit with the new
kernel/entry report; the existing8-second default boot and complete physical
fence/stock return remain. Hardware acceptance still requires scan, association,
DHCP and bidirectional traffic.

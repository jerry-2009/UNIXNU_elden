# Consolidated first UMAC failure

The tested OEM per-register wake path initially works, but its first PMF access
later times out while polling the real scratch register. Subsequent all-ones
values in that candidate are refusal sentinels. They are not raw CE or PCI
observations. Repeating wake-only experiments would not resolve that distinction.

This explicit observation gathers two complete states: stage12 after pdev and
rfkill setup, and stage90 at the first actual failed UMAC handshake, before
dropping its successfully acquired MHI reference. It preserves the qualified
control path and failure latch. It never forces new wake, resets or ring setup.

The PCI unit reads21 raw existing BAR registers: MHI control/status, UMAC request
and scratch, global reset, remap/identity, WLAON power/watchdog/cold reset,
Q6 cookie/warm entry and CE3 configuration/pointers. It excludes the read-clear
WLAON reset-cause register. Raw window selection still uses the existing PCI
accessor and its lock/readback; sampled values are not an atomic snapshot.

The current native worker reads47 words from its existing owned mappings:
endpoint config/command/BARs/device and link status, root link/MSI receiver,
outbound iATU window, PCIe GCC resets/GDSCs/votes/RCGs/branches, TCSR and the
retained PERST/CLKREQ GPIO window. It does not add maps or write controls.
Every word retains its read status, and the owner/epoch admission is checked
again after sampling. Link/config presence is not proof of UMAC readiness.

`tools/build_wifi_first_failure_native.py` builds the retained worker plus this
physical observer. `tools/build_wifi_first_failure.py` changes only the PCI and
core observation sites in the125-object runtime. Their matched reports are
consumed by `tools/build_wifi_net17_kernel.py` and the normal boot auditor.
The qualifier regenerates the exact source delta and checks the source/object
identities, two-stage bound and matched physical provider.

The test runs the actual physical observer with modeled MMIO/owner and retains
the failed first composition attempt. It does not prove any device condition.
Hardware acceptance still requires a complete captured pair and the existing
physical return/full stock restoration.

See [build evidence](../../../docs/evidence/wifi-first-failure-20261120.json).

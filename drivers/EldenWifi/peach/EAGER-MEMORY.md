# Peach Host Capability memory declaration

The prepared Ath12kWifi QMI source unconditionally sends an added Host Capability
TLV `0x33`, selecting on-demand host memory. The actual TB322FC stock
`wlan_firmware_service.ko` contains the complete69-element Host Capability
encoding table with an EOT marker; that table has no TLV `0x33`. The public
vendor source `d50b305f7da9e14715a25120a4ac7b1a4b8b97c3` also omits that field.
The stock CNSS request uses this table, as its actual relocation proves.

This source-supported contrast leaves the two demand-memory fields zero for
Peach only. Other targets retain the original extension. The existing QMI
memory indication, allocation and response paths, firmware, MSI/wake capability,
power policy, credits and rings are unchanged. It does not fabricate successful
allocation or change a firmware response. No evidence yet proves the extension
caused CE3/UMAC loss; the next full WMI/scan trial determines its effect.

The actual-state contrast previously showed unchanged PCIe config, BARs,
link/decode, iATU and GCC state at UMAC loss, while raw WLAON status changed and
CE3 configuration cleared. That narrows the next investigation but does not
identify which firmware or power condition caused it. The MSI enable word
`ffffffff` is an expected full vector-enable mask; the observer's generic
all-ones classification was diagnostic-only and is not a decode failure.

`tools/build_wifi_eager_memory.py` consumes `--runtime-build`, the qualified
`--parent-build`, `--llvm` and a new `--output`. It replaces one QMI object and
retains124 objects. The qualifier regenerates the exact delta and checks the
consumed source/object. `tools/test_wifi_eager_memory.py` takes `--cc`,
`--qmi-source`, and a fresh `--output`; it compares the actual old/new request
body across hardware/options and original QMI failures using modeled transport.

Original binary modules remain private workbench assets. The published evidence
contains only their hashes, the decoded structural table and scoped findings.
See [build evidence](../../../docs/evidence/wifi-eager-memory-20261120.json) and
[first-failure hardware record](../../../docs/evidence/wifi-first-failure-hardware-20261120.json).

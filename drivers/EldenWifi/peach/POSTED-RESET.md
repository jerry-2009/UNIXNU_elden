# PCI global-reset write completion

The qualified Elden PCI runtime omitted the readbacks added by Qualcomm's
ath12k commit `55f3aa06951cac78b0206bde961c8cf11929a27a`. ArmadaOS's pinned
TB322FC source `6f97250ead155fc3b980856323e99a4623dae73d` includes that change.
Sheng's `chipPowerUp()` also reads register `0x3008` after each reset write.

PCI writes may remain posted while the host starts its delay. Reading the same
register flushes the write before the existing 10ms delay. The patch adds those
two reads to the exact qualified PCI source and reverses byte-for-byte to it.
Reset values, delays, subsequent window restoration, CE configuration, WMI
credits, firmware and other runtime units remain the original ones.

This is an upstream correctness fix, not proof of the observed CE3 failure's
cause. The upstream test report names QCN9274, not Elden. The local host test
exercises the actual old/new reset body with modeled posted writes; device
WMI/scan validation is separate.

From a qualified runtime build, use `tools/build_wifi_posted_reset.py` with
`--runtime-build`, `--parent-build`, `--llvm` and a new `--output`. It recompiles
one PCI object, retains the other 124 objects, verifies its inputs and symbol
interface, and supplies the report for `tools/build_wifi_net17_kernel.py`.
The boot qualifier regenerates the exact patch and verifies the consumed PCI
source/object. `tools/test_wifi_posted_reset.py` runs the host test with
`--cc`, `--pci-source` and a new `--output`.

The parent is the combined OEM mode/sideband/WAKE-capability runtime. For this
diagnostic chain, individual build inputs and object identities remain explicit;
this document does not claim a new complete clean-build run.

See [signed build evidence](../../../docs/evidence/wifi-posted-reset-20261120.json).

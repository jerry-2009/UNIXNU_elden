# SM8750 portable scan candidate

This is an explicit Y700 TB322FC / SM8750 / Peach HW2.0 scan candidate.
It connects Leo Zhang's hardware-tested Piano CE/HTC/WMI/HTT protocol to
our existing PCIe, OEM firmware/QMI, NC-memory/SMMU and physical return path.
It is not yet a working iPadOS Wi-Fi interface.

The selected donor is [lenzhang/UniXNU-xiaomipad8pro](https://github.com/lenzhang/UniXNU-xiaomipad8pro),
commit `2438556c77c90c22c7b76e57eb8b40c44b35f1af`. Its dated
[November 14 results](https://github.com/lenzhang/UniXNU-xiaomipad8pro/blob/2438556c77c90c22c7b76e57eb8b40c44b35f1af/docs/results-2026-11-14.md)
record WPA2 keys/authorized port, DHCP, gateway/public pings, DNS, HTTPS200,
sleep and firmware-crash recovery. November13 records18 scanned networks;
November17 records a join through the macOS system interface. These are
reported hardware observations with run identifiers and logs, not a new
independent test of the donor tablet. The early paragraph in its component
README predates those results.

The donor runs macOS27.3. Only portable protocol code is imported here;
no Piano IOKit/Apple80211 ABI, PMIC, GPIO, PCIe, SMMU or firmware is copied.
Y700's own firmware has different bytes and remains unchanged.
`upstream/source.json` hashes every imported Git blob; `upstream/LICENSE`
retains Leo Zhang's BSD-2-Clause-Patent notice, and `UPSTREAM` identifies its
earlier Sheng and host-tested Pagani origins.

## Integration

The existing Linux MHI/QRTR/QMI path loads and checks the OEM assets first.
Only the explicit compiled `ELDEN_WIFI_PORTABLE_SCAN_TRIAL=1`, Peach HW2.0
and observed SoC identity `40210200` select the portable path at the real
firmware-ready callback. The normal/other-device core path is retained.
The donor CE rings use direct chip offsets and do not advertise the old
QMI shadow table. Their buffers use one4MiB allocation from the existing
checked 32-bit IOVA/NC arena, not arbitrary physical addresses.

`PortableScan.cpp` keeps the large CE/Link/HTT objects in BSS to avoid XNU's
small kernel stack. It uses the original MAC input, genuine firmware credit
reports, capability/ready events, regulatory channel list, and the donor's
two-round passive scan: the second runs with announced HTT receive buffers.
Only aggregate counts/state are logged; no SSID, BSSID, key or frame payload.
Protocol errors stay errors. No cfg80211 station or network interface is
published before real association. The iPadOS17 network bridge remains
present but its stage4/MAC publication gate stays closed in this scan trial.

Return closes the portable producer, attempts bounded protocol drain,
disables its rings, then executes the original real PCI shutdown and native
BM/transaction/MSI/PERST fence. A timeout never counts as drain success;
all DMA memory/state are retained to physical reset. No release or clock
guess is used to force a successful return.

## Build and verification

All effective source is in this repository. Build paths below are explicit
inputs from the documented clean-source and qualified incremental builds;
the new builder has no hard-coded WSL, v99 or workbench location.

```text
python tools/build_wifi_portable_scan.py --runtime-build ORIGINAL_125_OBJECT_BUILD --parent-build EAGER_MEMORY_RUNTIME --llvm LLVM_BIN --output NEW_RUNTIME
python tools/build_wifi_net17_kernel.py --parent-build SERVICE_SCAN_KERNEL --worker-build FIRST_FAILURE_WORKER --net-build STATION_STRIDE_NET17 --mac-phy-runtime NEW_RUNTIME --battery-admission-build BOARD_STATE_BATTERY --clean-build CLEAN_SOURCE_BUILD --original-kernelcache ORIGINAL_21H461 --output NEW_KERNEL
python tools/test_wifi_portable_qualification.py --report NEW_KERNEL/result.json --output NEW_QUALIFICATION.json
```

The donor's exact `upstream/tests/wmi_host.cpp` is run under ASan/UBSan,
covering real imported CE/credit/codec/state-machine/receive-buffer functions.
`TestPortableScan.cpp` additionally exercises our actual owner/bounds/error
adapter; it checks that a timeout returns failure, rather than the state
number being mistaken for success. Model register memory/firmware is not
hardware acceptance. One failed host attempt used the standalone compiler
without its macOS SDK; a later attempt found that state/error return mismatch.
Both failed logs are retained; the final SDK-backed ASan/UBSan runs pass.

Four C units and one new scalar arm64/iOS17 C++ object are built;121 original
runtime objects are retained. Original exports/kernel imports remain;
full native link/prelink preserves30 Apple executable regions and the7124
entry delta.128 inherited qualification mutations and11 new portable
mutations are rejected. Inherited C warnings remain157/152/83/67; the new
portable C++ object compiles with `-Wall -Wextra -Werror`.

Signed candidate `8ecacf4418e6a3c033c1258ec8e9b411e66b6f0a974fca938633840513b9f0f3`,
session `104b424f174e7b92`, floor1738713600/footer0/parent3 passes package
and full payload audit. Hardware is pending at this document's creation.
Acceptance requires a real started/completed scan with at least one BSS,
then physical fastboot/full stock/root/green/original-setting restoration.
Association, DHCP, traffic, sleep and charging remain separate unmet goals.

Mac `lab/wifi-portable-scan-20261120/{runtime3,kernel1,entry1,package1}` and
workbench `edl_work/wifi-portable-scan-20261120` hold generated build outputs.
[Evidence](../../../docs/evidence/wifi-portable-scan-20261120.json).

## Hardware result

The single consolidated trial completed the actual two-round scan on Y700:
32 retained BSS (list capacity32),113 management frames,6HTT receive rings,
24CE sends/24completions/0CE drops. The final state629/error0 and actual
credit reports were observed. Protocol stop idle1/rc0, real BM-off/idle
transactions/MSI4/PERST-low, typed physical fastboot and full stock SHA/
root/green/original charge+radio+scan settings/sleep restoration passed.
The capture is310307B; the raw USB drop counter is recorded separately in
[hardware evidence](../../../docs/evidence/wifi-portable-scan-hardware-20261120.json).
Warm MHI reset is still unverified. Association/WPA2/DHCP/traffic and iPadOS
network publication are the next combined functional step, not already done.

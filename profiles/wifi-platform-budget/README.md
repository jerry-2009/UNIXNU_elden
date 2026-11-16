# v172 bounded MHI polling during platform shutdown

v171 entered the real registered PCI shutdown callback and reached MHI reset,
but did not return within the9-second WCN bound. The actual ath12k controller
sets `MHI_TIMEOUT_DEFAULT_MS=90000`; generic MHI shutdown can poll RESET clear
and READY separately using that limit before its later chip-reset path.

The explicit platform-shutdown entry now sets one monotonic2-second deadline
immediately before invoking the registered callback. Only MHI register polling
while this deadline is active uses it. With no platform deadline, the original
startup/recovery poll body and timeout remain unchanged. The deadline is shared
across RESET and READY waits, never renewed per call. A fresh read is still made
after expiry; a matching observed field succeeds, errors propagate and a field
that does not match returns actual ETIMEDOUT. A bounded attempt count also handles
a stalled host clock. No register values or success responses are fabricated.

Upstream shutdown continues after a reported polling error to its remaining
cleanup and chip-reset operations. DMA backing/objects stay retained. The native
layer still independently requires valid MHI reset/ready state, bus-master-off,
transaction idle, MSI drain/mask, PERST and real WLAN release before it reports
successful shutdown. A timeout log by itself is not hardware acceptance.
The5-second owned cleanup and9-second overall WCN return bounds are unchanged.

Host verification runs the actual original/new polling bodies with simulated
registers and clock: original startup timing, observed success/read error,
aggregate deadline, final fresh read, stalled clock and invalid delay cases pass
under ASan/UBSan. The updated real platform-entry/PCI-shim routing tests also pass.
Neither host fixture proves physical reset. Config/MhiStop and all native guards
reuse the already verified source fromv171.

Build `tools/build_wifi_platform_shutdown.py`, now including the MHI main unit,
then the same native/root/boot stages. Source182 pins, Apple30, entry7124 and26
critical call targets pass. Final Mac/workbench directory is
`wifi-platform-v172-20261116/{source1,route-host1,budget-host1,runtime1,native1,kernel1}`.
Kernel `628082699447e16decc2a94786b0be0aef0231bbab47e35c426766c5723551ec`.
[Current evidence](../../docs/evidence/wifi-platform-v172-20261116.json).
Full network and peripheral acceptance remains incomplete.

Signed candidate `136a8e092f41341bf74d84cd4e25e7ef3c5f5497c4d6e655b5f7ab34bff824c6`, session `340c4cbb73e913b5`.
All182 source inputs match Git index; entry/asset/FAT/AVB checks pass
(1738713600/0/3). Hardware validation pending.

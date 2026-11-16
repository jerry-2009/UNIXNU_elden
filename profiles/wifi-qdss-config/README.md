# v167 original Peach QDSS configuration

v166 reached real MHI Mission Mode and QRTR/QMI but stopped at
`failed to load exact Peach QDSS config: -2`. The pinned TB322FC Linux Peach
QMI flow (`drivers/EldenWifi/peach/upstream-peach.patch`) requests
`qdss_trace_config.bin` and expects a real segmented QMI transfer.

The resolver now maps only that request (bare or the existing PEACH/hw2.0
prefixes) to `image/peach/qdss_trace_config_v2.cfg` on the original modem_a.
The file is6237 bytes with SHA256
`94251904525f36f69092db8abde1f5198bd32c8c5fa482448e7076e0e3bc0eab`.
The Android file and retained complete stock modem backup agree. No firmware
bytes are added to Git; the fingerprint and exact alias are source-controlled.

The existing reader enforces partition geometry, FAT bounds, size and full
SHA256 before returning a buffer. Cache capacity now derives from the input
array instead of hardcoding7. Original file slots are preserved; QDSS is slot7.
The original six boot preflight files and bus-master admission are unchanged;
QDSS loads on demand when the actual QMI caller requests it. No fabricated
response, QMI bypass, timing/clock/power change or firmware modification.

`tools/test_wifi_firmware_cache.py --modem <stock-modem> --output <new-dir>`
passes9 actual-cache/FAT scenarios and72 ASan/UBSan checks. It verifies original
bytes and aliases and flips a byte specifically in QDSS's FAT data range;
the hash gate rejects and latches the error without publishing data or rereading.
Kernel allocation/locking/block services are modeled. This is not a QMI
hardware result. Previous8 scenarios remain, including failure/stop behavior.

Use `tools/build_wifi_firmware_cache.py` with the clean source-built SDK and
reference kernel, then `tools/build_pcie_native.py --control-transport` with
that firmware result and the qualified v165125-object runtime. Finally run
`tools/build_pcie_root_kernel.py` with the same MHI/prefault/unique/segmented/
memory-detail provider arguments as [v166](../wifi-control-transport/README.md).
The new firmware result explicitly selects `wifi-qdss-config` for packaging.
The v166 worker's complete object SHA is unchanged (`1dd01bae...`); only the
firmware-cache object changes behavior. Full kernel3465762a preserves core,
other members, Apple30, entry relation7124 and21 checked call targets;178
source inputs match. No new combined empty clean build was claimed.

Mac final components: `lab/wifi-qdss-v167-20261116/{source1,host1,firmware1,native1,kernel1}`.
Workbench mirrors them under `edl_work/wifi-qdss-v167-20261116`.
[Current evidence](../../docs/evidence/wifi-qdss-v167-20261116.json).
Full boot qualification and the hardware result are recorded below.

Signed candidate `432fd68822dc7fe31c87ff097d96082286beb43727285c84d3e9b3bf0986e703`, session `1e5fdb6c5d47aa36`.
Entry/asset/FAT/AVB independent audit passes (1738713600/0/3).
Hardware reached FW_INIT_DONE and Linux stage4/error0. A native scan request
was queued, but BSS remained0; the real supplicant service is not yet installed.
The original no-address warning also remains (upstream local-address fallback).

Graceful teardown is NOT accepted: mode-off QMI returned-12 and WCN exceeded
its9s wait, then the established typed platform-reset fallback restored stock
with the full SHA. Unlike v166, this capture has no native runtime-stop,
RESET/master-off/IRQ/PERST completion. Fix cleanup lifetime before the next
expanded hardware trial. Capture261567B/SHA8e608813/dropmax0/no reconnect;
post-disconnect counter unavailable. Android/root/green/settings restored.

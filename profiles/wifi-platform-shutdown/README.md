# v171 actual PCI platform-shutdown lifecycle

Linux platform reboot uses the registered PCI shutdown callback. The prior port
called module removal, which waits for an uncompleted MODE_OFF transaction.
[Source rationale](../../docs/WIFI-PLATFORM-SHUTDOWN.md) records the distinction.

`nw_wifi_platform_shutdown` closes UI/control, then the PCI shim calls the actual
registered `g_drv->shutdown(&g_dev)` and performs the real consumer unbind. Missing
registration, callback or driver data refuses; unbind failure propagates. Results
are latched, so the callback is not repeated. Driver structures and buffers remain
until platform reset. The original remove and failed-start cleanup are unchanged;
this does not claim to fix module unload or acknowledge MODE_OFF.

The exact prepared ath12k installs `ath12k_pci_shutdown`, which calls hardware
group power-down. Force-wake/MSI disable/MHI stop/software reset follow the same
source; the common software-reset operations are also used during power-on.
Peach's supports_aspm is true. Native Config now saves the initial Link Control
and allows only restoring those two ASPM bits during cleanup, preserving all
other control bits and zeroing W1C status writes. Wrong saved state, width, value
or unrelated-bit changes refuse. Any failed config write is retained by the native
wrapper and cannot become a successful platform-stop result.

The existing native MHI reset/ready, bus-master-off, transaction-idle, MSI drain,
PERST and WLAN-release checks still run independently after the callback. Missing
proof retains resources for platform-reset fallback. The5s cleanup and9s WCN
limits remain. No new PMIC/clock vote or generic MMIO access gate is introduced.

Host tests cover6 routing cases43checks (actual new entries; driver hardware
callback modeled),77 native transport/config/MSI cases334checks including ASPM
and W1C, and6 composed DMA/MHI cases135checks. The latter retain their documented
Linux/MMIO model limits; hardware acceptance requires the new full trial.

Runtime rebuilds nw_wifi and nw_pci, retaining the prior cfg80211 init object and
122 original objects. Config and MhiStop rebuild with matching headers. The v170
trace ternary is separately corrected to treat nonnegative qmi_txn_init returns
as allocated IDs; that diagnostic is not included in this candidate.

Mac `lab/wifi-platform-v171-20261116/{source1,route-host1,config-host1,mhi-host1,
config1,stop1,runtime1,native1,kernel1}`; workbench mirrors under edl_work.
Kernel `f2c6f6ce4c14e2eb833f7415c4f828ab9447f37e69286c009b7d099d0f16fd10`.
182 source inputs, Apple30, entry7124 and25 critical call targets pass. Hardware
and boot results follow in [evidence](../../docs/evidence/wifi-platform-v171-20261116.json).
Full peripherals, network and charging acceptance remain incomplete.

Signed candidate `851ee98471fde6081bdc1382d4d243a53bdf69ee87986e1739c5595cef1b0d60`, session `d9cddb9af79a73a1`.
All182 source inputs match Git index; entry/asset/FAT/AVB checks pass
(1738713600/0/3). Hardware reached stage4, entered the actual PCI shutdown callback, and reached
MHI reset handling. It did not return within9s; the configured MHI default is90s
per polling wait. The exact register value was not captured, so do not infer a
firmware defect. No ASPM/hardware-drain completion is accepted. Typed fallback,
full stock SHA and Android/root/green/settings restoration passed. See evidence.

The next explicit budget profile bounds only platform-reset polling and keeps
the original timeout return and later chip-reset path, followed by independent
native hardware checks. The tested v171 image remains tied to commit acbfaf5.

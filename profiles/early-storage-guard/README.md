# v150: watchdog before kernel UFS takeover

Normal vdog=3 now arms the existing Y700 Gunyah watchdog after SDAM fastboot
routing is verified and before this driver's UFS operations. The existing SMP
worker pets during its bounded readiness wait, then adopts the same context;
there is no second timer/owner or repeated enable. Its RAM Data/USB/per-core
admission stays unchanged. Bark27s/bite30s, SDAM addresses and firmware are unchanged.
This covers kernel UFS entry, not SEC/DXE or earlier kernel bootstrap.

The normal run passed EARLY_ARM rc0/control1/elapsed0, protected UFS entry before
BSD root, and SMP_ADOPT rc0. Existing eight-core work/timer/IPI admission reached
all ff/error0. Root, GUI and synchronized stock Android restoration passed.

The same kernel's controlled vdog=4 test creates no SMP/petting worker, stops
before UFS, masks IRQ/FIQ and drains only USB while reading raw time. Other
memory-backed bootstrap work may already have occurred. A120-second PSCI fallback
remains, distinct from the independent watchdog.

The PC received the exact masked-stall marker, session and boot nonce. A transport
error was observed33.726s later and fastboot current-slot=a responded46.583s after
the marker, before the120s software fallback. No fallback marker, BSD root, SMP
adoption or PC reboot request was observed. The supervisor source was checked to
send no reset/UI control command during the test window. This supports hardware
expiration at this stage;46.6s includes reset, bootloader and USB re-enumeration,
not a46-second hardware timeout. The assessor uses a30s margin before the software
fallback; an arbitrary45s host cap would mix watchdog and bootloader time.

| Candidate | SHA256 | Session |
| --- | --- | --- |
| Normal | 43624aa70777de7577089a23a54061ea7578e4262f9e77ce3ae09775413410fc | e4b1779771d230a4 |
| Stall | c67f018f9d4b2acf5c51556d523a9cbddfb29083d4db984a6e7e4105cf5acd40 | 005391fd1ec918c6 |

Only the FAT menu/session member differs; kernel, entry, FD, loader, Data and trust
assets are identical. Stall packing/audit requires explicit --early-stall, and
full image audit rejects the stall image without it. Normal boot uses vdog3.
Both keep rollback1738713600/footer0/parent3 and the existing recovery deadlines.

Normal capture3102556B/drop59 has no discontinuity. Stall capture13411B/drop0
retains its final write-timeout boundary and has no reconnection. Both returned
to physical fastboot, restored stock8b8e72da by full SHA, and passed Android/root/
green/boot/charging-setting verification; sleep requested, all jobs terminated.
See [hardware.json](hardware.json) and [validation.json](validation.json).

## Reproduction and limits

EarlyStorageSource.py derives current UFS (including v149 medium properties) and
the ce63730b recovery header. One UFS object changes. Exports, original initializer
targets, other archive/core members, Apple30 execution ranges, entry and AVB pass.
Native disassembly contains the expected IRQ/FIQ mask instruction.11 ASan/UBSan
host cases execute transformed arm/wait/adopt/stall code with the byte-matched WDT
core; assembly, scheduling and SMC are modeled there, separately from hardware.

Add --early-storage-guard to the existing native17 charging clean-build chain; it
includes the storage-medium parent. Staged native builds use build_charge_verification.py
--early-storage-guard. Individual native/entry/normal+stall packaging/audit stages
ran; the newest combined empty-directory command was not repeated. --early-stall
is a packaging/audit qualification option, not a daily-use boot default.

Next UFS wait/IRQ/queue/DMA work may use this guard, but still requires DMA bounds,
authentication, write gates and data-integrity checks. A watchdog does not make
unsafe DMA or writes safe. Full firmware-to-EARLY_BOOT coverage remains separate.
Charging/endurance and the remaining peripheral Goal are still incomplete.

Final Mac: isolated/early-storage-v150. Workbench: edl_work/early-storage-v150-20261115,
live-early-storage-v150-20261115 and live-early-storage-v150-stall-20261115;
lab/records/early-storage-v150-20261115 holds the evidence.

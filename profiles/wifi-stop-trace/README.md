# v169 consolidated Linux shutdown trace

v168 admitted the original worker's bounded cleanup but did not return from
`nw_wifi_stop` within the unchanged9-second WCN window. Its exact child call is
unknown. This diagnostic places enter/leave markers around45 calls across
`nw_wifi_stop`, PCI removal and the core group/stop/destroy functions. Compound
statement wrappers preserve unbraced-if semantics; removing the exact wrappers
recovers each prepared source byte-for-byte. No return, original call, timeout,
register or power policy is changed.

The native quiesce wait additionally reads the existing4-word `nw_wifi_where`
array at iteration0/2000/4000/6000/8000, still bounded by the original deadline.
It reports whether two reads matched, not that they are transactionally coherent.
`tools/analysis/resolve_wifi_where.py` resolves the relative function address
against the exact native Mach-O (ASLR cancels in the relative offset). Its output
is a dispatcher observation, not a sampled thread backtrace.

Build `tools/build_wifi_stop_trace.py` with the qualified prepared runtime,
lifecycle and v165 init-trace outputs; it rebuilds nw_wifi, ath12k_core and
ath12k_pci. The existing cfg80211 init object and PCI lifecycle object are retained,
as are120 original objects. Symbols/header inputs/renaming and total125-object
binding are checked. Then use the native and root builders with the same v168
providers; the stop-trace result selects this explicit profile and retains
all original boot arguments/default/countdown/recovery.

Mac: `lab/wifi-stop-v169-20261116/{source1,runtime1,native1,kernel1}`; workbench
mirrors under `edl_work/wifi-stop-v169-20261116`. Source182 pins, Apple30,
entry7124 and23 existing critical calls pass. Kernel `c46fd07612053981fd375ba7180f8d83710fe287ac7e03583f1cf15255cfb111`.
Three C objects retain83/157/120 warnings; the native worker retains1 shadow
warning. No broad warning waiver or hardware acceptance claim. The host-only
resolver check used synthetic markers and a real kernel's negative symbol offset.

[Evidence](../../docs/evidence/wifi-stop-v169-20261116.json). Full peripheral,
charging and network requirements remain incomplete. Do not promote this trace
as a new stable daily image or extend the shutdown deadline to mask a stall.

Signed candidate `b5c5177a2d0898e220195e04a86fabe090394d57f746b5d877d87c8c87bc8a31`, session `4487394d1c0b2db3`.
All182 source inputs match Git index; entry/asset/FAT/AVB checks pass
(1738713600/0/3). Hardware localizes the unfinished call to `ath12k_qmi_firmware_stop(ab)`
(core.c:7). Its preceding mainline/control/PCI reset+dump cancellation/group MAC
cleanup and core-lock steps return. Four dispatcher samples are idle kind0,
depth0 with advancing timestamps; this is not a backtrace. The MODE_OFF send
and reply-completion details are not yet observed. Prepared QMI and MHI workqueues
already have the IO-completion flag, so a guessed flag change would be redundant.
The configured QMI wait is10s and the WCN return bound9s; do not just extend it.

Stage4 remains intact. No native shutdown/reset/master-off/IRQ/PERST completion.
The typed platform-reset fallback and full stock Android/root/green/settings
restoration passed. [Hardware evidence](../../docs/evidence/wifi-stop-v169-20261116.json)
contains the complete trace and capture limits.

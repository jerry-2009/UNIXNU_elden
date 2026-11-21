# v177 session-aware diagnostic scan

The v176 scan event went to a client whose INFO initialization failed. This
profile samples the current control session only after a successful INFO reply
was actually enqueued to it. Failed enqueue, non-INFO replies, error status,
wrong wire session and a disconnected/replaced client cannot qualify.

The existing native control lock protects the delivery marker; it is never held
across `ctl_enqueuedata`. Connect/disconnect clear the marker. The wireless worker
samples it, sends at most one successful request per observed session and keeps
the original three-attempt total, deadlines, shutdown and global upstream UI
queue. This is diagnostic request scheduling, not a replacement Wi-Fi protocol
or a claim that enqueue success proves client parsing or a completed scan.

Use [v176's recipe](../wifi-service-control-trace/README.md) with
`build_wifi_service_native.py --control-trace --service-scan`. The v175 core and
all helper/trust/cache/firmware inputs remain unchanged. The full linker selects
this distinct profile. `test_wifi_control_native.py --service-scan` runs the
actual native predicate and extracted scan block with the real pinned control
queue. It covers failed/error/malformed/stale replies, reconnect, stop, one
request per session and the three-attempt bound, plus existing seven socket
scenarios, stats ABI, redaction and log cap. Host XNU services are modeled.

Hardware did **not** reach scanning: first INFO was NOT_READY3, later replies
were DRIVER_FAILED9. WMI command16387 (`WMI_PDEV_SET_PARAM`,0x4003) repeatedly
timed out while opening MAC operations, returning−11. Credits were0; CE ring
diagnostics showed hardware/source/completion position differences. These do
not by themselves identify the missing IRQ/work/DMA stage. No successful INFO
was observed and the diagnostic scan stayed closed. BSS remains0.

Preserved v175 logs have the same WMI timeout (30 occurrences); v176 has none
and completed INFO. This confirms the earlier success was not a stable fix.
Next compare native MSI latch/enable/mask/pending/error and logical CE completion
state at the first WMI failure. Do not mask this with fabricated credits,
timeout extensions, unqualified IRQ polling, or guessed clock/voltage changes.
The firmware's DDR/file comparison diagnostic does not establish RAM corruption.

Physical DMA fence, MSI stop, PERST-low, WLAN stop, typed return, physical
fastboot, full stock SHA and Android/root/green/original settings restoration
all pass. MHI warm reset remains unverified. Capture285382B/drop8; no reconnect,
no post-disconnect counter. All jobs terminal. Full peripherals remain incomplete.
[Evidence](../../docs/evidence/wifi-service-scan-v177-20261116.json).

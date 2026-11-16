# Wi-Fi native control transport

v165's hardware trace reached `nl80211_init` and returned `-16`. The linked
implementation is `src/nw_cfg80211_control.c` in Ath12kWifi at
`5f7f5a8a9f02f7ab45ed10a2f226e348c519a838`, not unused Linux
`out/cfg80211/nl80211.c`. It maps any failed `nw_wifi_control_bind` to EBUSY.
The real queue requires `nw_wifi_control_transport_set` first; Elden had not
installed it. A production-queue test reproduces NOT_READY before installation
and successful binding after installation.

`ControlNative.inc` adapts successful Sheng's `WifiProbe.cpp` method
(reference `e8937177309d88c93b305a57bad147fd5fac8a86`): register the privileged
AF_SYSTEM kernel control `org.unixnu.wifi.control`, install send/wake callbacks,
then call `nw_wifi_start`. The wire protocol and authentication remain upstream.
No fabricated/headless successful bind, packet payload logging, or hardware
register change is used. Attribution is in `drivers/EldenWifi/LICENSE.sheng`.

The kernel callback copies a request from its mbuf into the upstream bounded
queue. Linux work runs on the existing Wi-Fi worker. Clients are session-bound;
old sessions, oversize messages, failed copies and operations after stopping
are rejected. Each received mbuf is released. The adapter releases its lock
before `ctl_enqueuedata`, preserving Sheng's socket lock ordering. Stop is
terminal, prevents further admission, and lets the original worker shut down
the control queue before MHI/reset teardown. Socket reference/lock remain until
platform reset; disconnect releases its owned client. This is not hot-unload.

Build after the qualified MHI/firmware/DMA components described in
[the MHI profile](../wifi-mhi-runtime/README.md). Pass `--control-transport` to
`tools/build_pcie_native.py`; keep the existing complete provider arguments,
including the current cold-owner QmiPower. It imports only verified kernel
header aliases from the source-built NativeHost closed VFS, checks collisions,
and does not enable filesystem fallthrough. Full `build_pcie_root_kernel.py`
uses the same `--mhi-runtime --prefault-memory --unique-memory
--segmented-memory --memory-detail` options and selects this explicit profile.
All 125 reviewed v165 runtime objects are reused; only the native worker changes.
The profile is an incremental full-kernel stage over a source-built baseline;
it is not a claim that a new single-command empty build has been rerun.

Tests: `tools/test_wifi_control_native.py --runtime-build <prepared-runtime>
--component-repository <Ath12kWifi-clone> --output <new-directory>`. It verifies
original control source bytes, ABI enums/layout/callback types, runs the official
real-thread queue test with an additional missing-transport assertion, then
seven native adapter scenarios using the same production queue. ASan/UBSan pass.
XNU sockets/mbufs are modeled; those tests are not native socket or radio acceptance.
First two ABI comparison fixtures failed C-linkage/namespace compilation and
were corrected without changing production source; failed records are retained.

Native object `1dd01bae1e3d8520dd692288f2f7cdad01ee8c849ad5a72f95dfb06547ac55f4`;
binding `4ce7a39d9f7adb1422bf8bf34f62fc5e829fef84594532e9df070d1e01f201d6`.
One local-name shadow warning remains, not a type/conversion warning.
Kernel `f847af90b826f2fc57f74ea3569b2cb6f597587177b3da99662ca0cc8d925f3b`.
The complete kernel preserves 30 original Apple executable ranges, core/other
archive inputs and entry relation7124; 178 source inputs match and 21 direct
call targets retain prelink bytes. Boot/hardware results will be recorded after
qualification. No device DMA, firmware readiness, scans or networking is yet
claimed for this revision.

Mac output: `lab/wifi-control-v166-20261116/{source4,host3,native2,kernel2}`.
Workbench: matching `edl_work/wifi-control-v166-20261116`. Earlier missing header
aliases (native1) and a helper's stale native1 path (kernel1) remain as failures.

Signed boot: `8d4917a338cbfc087c817cfdb5ba13882174917d2afba63aa8acb18adb9a261c`; session `401a0d3a1b943912`.
Full independent boot/asset/AVB audit passes, floor1738713600/footer0/parent3.
No hardware result yet.

# v168 bounded native Wi-Fi cleanup

v167 reached real firmware-ready stage4 but its stop path reported QMI mode-off
ENOMEM, then exhausted the existing9-second WCN return window. The native code
closed DMA before calling `nw_wifi_stop`; normal WLAN admission/epoch was also
revoked before quiescence. The old host fixture did not send a DMA-backed shutdown
request and therefore missed this lifetime defect.

The new adapter separates closing ordinary requests from final/fault DMA stop.
After the control endpoint and ordinary admission close, only the originally
recorded Wi-Fi worker may allocate/map during Linux shutdown, for at most5seconds.
The real native predicate checks provider, immutable epoch, original thread,
entered/started/not-returned state, cleanup phase/deadline, retained root/BAR/PERST
and SMMU/MSI fault state. No constant-success callback, new bus-master grant,
power vote, recovery timer extension or wider DMA mapping is added.

WlanPower still revokes its public lease before quiescence. Its established
callback contract retains physical power until the native worker stops and
PERST is asserted. The private cleanup check relies on that retained-owner
contract; it does not reopen the public WLAN lease. Any final DMA stop or hardware
fault remains terminal. The final sequence is Linux protocol shutdown, close all
DMA, verify MHI RESET/READY and bus-master-off/transaction idle, drain/mask MSI,
assert owned PERST, then permit WLAN power release and SMMU withdrawal.
Backing memory and tables remain retained until platform reset, including failure.

Tests use actual DMA arena/adapter, config/MSI/reset and QMI binding with modeled
XNU services and Linux protocol shutdown. The precise previous runtime body
(SHA480960b4) rejects the same modeled DMA-backed shutdown request; the repaired
body permits it despite public lease withdrawal. Separate tests cover other
threads/owners/epochs, deadline expiry, final stop and SMMU/MSI fault denial.
They do not execute real Linux QMI or establish the exact live -12 return site.

Run `tools/test_wifi_dma_native.py --output <new>` and
`tools/test_mhi_runtime.py --component-repository <Ath12kWifi>
--original-runtime <v167-MhiRuntime.inc> --output <new>`.
The original input must have the exact reviewed SHA; no test rewrites it.
Build the source-derived WCN adapter and SMMU DMA binding, then the native PCIe
worker and complete root kernel with the existing MHI/control/QDSS arguments.
The SMMU component deliberately requires the strong native cleanup predicate;
the full native link must resolve it. No weak or generic missing-import waiver.

Initial final components are under `lab/wifi-drain-v168-20261116` on Mac and the
matching workbench `edl_work` directory. Updated evidence will record exact
source/test/build directories, signed boot and hardware scope. Do not reuse old
native-contract.json or claim a new combined empty clean build was run.
The first hardware test must preserve stage4, then prove native stop and the
full stock-restoration chain. Scan/networking and charging remain incomplete.

Final builds: Mac `source3/dma-host2/mhi-host3/wcn1/smmu2/native2/kernel2`
under the directory above (WCN source1 is unchanged).
16 actual native callback scenarios / 127 checks passed; IOKit, power, SMMU and barriers modeled.
6 native MHI runtime scenarios / 135 checks passed; actual DMA arena/adapter/QMI binding/config/MSI/reset, Linux protocol and hardware modeled.
Original reproduction: PASS original shutdown reproduces DMA refusal after public power withdrawal.
Kernel `087306d055f4483cb32173ad032cb8bd4bb107b90536a1d9acf9ea691bb113b6`; native worker `59b373efe04f6723b9bafd797024be2b9f3fda2a1af6224be1da20c554a3313e`.
178 source inputs/Apple30/entry7124/23 direct calls verified. Native worker retains
one existing name-shadow warning; SMMU retains its existing ready int-to-uint32
warning, Domain has none. The125 reused Linux objects retain their prior warning
audit limits.

Signed candidate `29a919357feceb6d3d5fbd1c42e077e6a4119f1be29ed211f4cb2a2c5dfaf40f`, session `de78ea6f9db8e66d`.
Entry/asset/FAT/AVB independent audit passes (1738713600/0/3).
Hardware preserves FW_INIT_DONE/stage4 and records cleanup=0. The earlier
QMI mode-off -12 is absent, but no mode-off completion is observed either.
`nw_wifi_stop` does not return within the bounded WCN window; no native
RESET/master-off/IRQ/PERST completion is recorded. Typed platform-reset fallback,
physical fastboot, full stock SHA and Android/root/green/settings restoration pass.
Thus this is not accepted as graceful shutdown. Next locate the exact subcall
with one consolidated stop trace, keeping the9s reset contract unchanged.
Capture259020B/SHA3edd240e/dropmax0/no reconnect; no post-disconnect counter.
[Evidence](../../docs/evidence/wifi-drain-v168-20261116.json).

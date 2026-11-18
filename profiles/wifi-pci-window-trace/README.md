# PCI window qualification for CE3 HP/TP reads

v187 observed HIF HP/TP0/0 while coherent DMA TP was8. This profile retains the
CE3 first-failure observer and wraps those same two HIF reads with PCI metadata:
requested internal offset, actual BAR offset/selected window, static mapping,
CE/DP bases, cached and hardware window register, wake result and returned word.
The existing read/write/window/wakeup/release statements are unchanged. The only
additional hardware read is the already-used window register below WINDOW_START.
No shadow register is read and no extra producer, credit, clock or timeout write
is introduced.

`PciWindowTracePatch.py` requires v179's exact instrumented PCI source hash and
is uniquely reversible. It records effective offsets in every actual read branch
and logs only while the explicit SRNG read wrapper is active. Normal reads retain
the original behavior. Individual observations are not coherent atomic snapshots.

`test_wifi_pci_window_trace.py` exercises30 original/patched function scenarios
with ASan/UBSan: direct/static CE/static DP/dynamic/MHI paths, wake errors,
release/count/offset equivalence and bounded formatting. Window/hardware are
modeled; the compiled ARM64/iOS17 runtime separately verifies scalar code,
imports/exports, no initializers and inherited hashes.6 changed/119 retained
runtime units include the prior IRQ/HTC/CE/WMI observations.

Build `tools/build_wifi_srng_trace.py --pci-window-trace --runtime-build BASE
--credit-build V179 --llvm LLVM --output NEW_RUNTIME`, then use the maintained
service-native/kernel recipes in [wifi-srng-trace](../wifi-srng-trace/README.md).
`tools/build_wifi_srng_boot.py` packages either explicit diagnostic profile.
Mixed/native/unit-count variants are refused by actual qualification checks.

The next hardware window must preserve the established SMP/DMA/MSI/PERST and
typed return/full stock/root/settings gates. Allow the original runtime worker
its terminal path; do not initiate an early20-second reset just because the
snapshot arrived, and do not extend existing safety deadlines. This remains a
diagnostic profile and does not claim scanning or networking acceptance.

v188 hardware qualification (2026-11-18) confirms the original Peach dynamic
window37/register3278/readback40000037 and wake0 at actual BAR offset86400.
Direct CSR HP/TP0/0 still differs from coherent DMA TP8; the window result is
not proof of failed notifications or firmware consumption. Verify pointer read
semantics and the real completion path next. The original90-second runtime
return captured actual DMA fence, master-off/idle, MSI drain, PERST and WCN stop;
warm MHI reset remains unverified. Full stock/root/green/original settings and
sleep were restored; startup radio-restore failure is retained with a final
successful closure. See [hardware evidence](../../docs/evidence/wifi-pci-window-v188-hardware-20261118.json).

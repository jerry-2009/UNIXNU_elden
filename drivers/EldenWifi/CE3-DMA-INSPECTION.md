# First-failure CE3 and DMA inspection

The normal candidate, MHI hold, second UMAC/VDEV candidate and direct-HP
contrast all retain the early CE3 HP16/TP8 first-PDEV failure. One UMAC run
advanced16 descriptors, so that earlier progress is not a stable fix.

This candidate collects the missing evidence at the original first
`ath12k_wmi_cmd_send` EAGAIN timeout, before the upstream forced-RDDM path.
It does not use the previously interrupted mode-response observer.

-18 exact CE3 R0/R2 register reads: base/size/ID/status/MISC/remote-tail address,
  interrupt setup/status, MSI target/data, direct HP/TP. Only existing HIF
  accessors are used; their normal dynamic-window/wake operations remain.
- At most4 currently pending CE3 descriptors, including address/length/metadata
  words and equality to the retained skb bus address.
- Actual native owner validates that buffer with the existing DMA arena and
  SMMU status, then CPU read/write PAR and NC attribute44. Its physical address
  must match the qualified backing plus the bus offset. This proves a CPU
  translation/backing comparison, not hardware SMMU translation or successful
  device reads. No new mapping allocation, cache operation or table write.
- Only fixed HTC, WMI command and TLV headers are logged. Parameter values,
  packet contents, MAC/SSID, keys and firmware bytes are excluded.

The native inspector requires the original wireless thread, active owner/epoch,
live arena/SMMU, valid complete range and no shutdown/fault. First-only capture
and exact CE3 geometry bound all reads. Source-tested VDEV fix and original
shadow notification path remain, with the matched explicit UMAC worker.

27 actual observer/native verifier scenarios pass ASan/UBSan; hardware, CPU
PAR, SMMU status and kernel ownership are modeled.31 qualification mutation
cases check pairing, read/record bounds and privacy declarations. One WMI unit
is rebuilt,124 runtime objects retained; native worker adds only the inspector.
WMI632 and native1 inherited warnings remain. All actual imports resolve,
scalar/no initializer, full native/prelink,30 Apple execution regions and
entry delta7124 pass. The dependency audit explicitly accepts the newly
consumed pinned wifi7 descriptor header and canonicalizes its existing`../core.h`
spelling; no other headers change.

The preserved initial tests show an incorrect include anchor, C-to-C++ aggregate
warning and clang C-driver omission of C++ linkage; the final host3 fixes only
the test fixture/compile selection. Runtime1's newly consumed descriptor-header
rejection is retained; runtime2 audits its exact pinned hash.

```text
python tools/test_wifi_ce3_inspect.py --cc CLANG --wmi-source VDEV_WMI --output NEW_HOST
python tools/build_wifi_ce3_inspect.py --runtime-build BASE --parent-build VDEV_RUNTIME --llvm LLVM --output NEW_RUNTIME
python tools/build_wifi_net17_native.py --umac-hold --dma-inspect --parent-native SERVICE_NATIVE --net-build NET --reference-kernel NATIVE --clean-build CLEAN --llvm LLVM --output NEW_WORKER
```

Compose through`build_wifi_net17_kernel.py` and the full entry/package audit.
Signed image`32e4a34d65dd674fbe2313114326b7073f9422ba73799c7b380236b758c42f99`,
session`69c7185df67b4674`, floor1738713600/footer0/parent3. Hardware pending.
Require complete first-failure lines and full physical stop/stock restoration;
no scanning, association, DHCP or traffic acceptance yet.

[Evidence](../../docs/evidence/wifi-ce3-inspect-20261120.json).
Mac`lab/wifi-ce3-inspect-20261120/{host3,runtime2,worker1,kernel1,entry1,package1}`;
workbench`edl_work/wifi-ce3-inspect-20261120`.

# Match capability-array allocation to its element stride

The fixed TB322FC Linux tree includes
`26f8f87f0a556e7984366c64cebc16d49e15d22f`, upstream
`4c6eb712a91fa079be6f9f1419c96e0ad2227081`. Its actual callback allocates full
`ath12k_wmi_mac_phy_caps_params` elements and only then clamps the copied TLV
length. That fix has upstream WCN7850 hardware evidence. It does not change a
WMI request, CE descriptor, credit count, pdev selector or firmware input.

The retained Elden runtime's older callback allocates `tot_phy_id * len` but
indexes the destination as a full-structure array. For short TLVs the second
and later slots can extend past the requested allocation. The reader uses the
same full element stride. In the actual consumed header this stride is236B.

`MacPhyStridePatch.py` ports only that allocation/copy correction to the plain,
hash-bound WMI source. Linux7.0 lacks `kzalloc_objs`; the equivalent explicit
`(size_t)tot_phy_id * sizeof(*mac_phy_caps)` is used. Both tag/count refusal,
allocation-error handling and copied byte count remain unchanged.

`test_wifi_mac_phy_stride.py` executes the actual old and new callbacks in70
cases with short/full/oversize TLVs, multiple elements and refusal/allocation
failures. The allocator provides a larger test backing so the old callback's
requested-size overrun can be measured without an out-of-allocation write.
ASan/UBSan pass. This reproduces the source defect, not hardware memory
corruption or the cause of the Y700 WMI timeout.

`build_wifi_mac_phy_stride.py` recompiles one real `ath12k_wmi.o` and links it
with the other124 retained objects. Imports/exports remain identical; CE,
MHI, PCIe, IRQ, cfg80211 and firmware objects retain their hashes. Scalar
iOS17 compilation passes with the original632 WMI warnings retained.

```sh
.venv/bin/python -B tools/test_wifi_mac_phy_stride.py \
  --wmi-source /path/to/prepared/wmi.c --wmi-header /path/to/prepared/wmi.h \
  --cc /path/to/clang --output out/stride-host
.venv/bin/python -B tools/build_wifi_mac_phy_stride.py \
  --runtime-build /path/to/source-built-runtime \
  --platform-build /path/to/source-built-platform-budget \
  --init-build /path/to/source-built-init --llvm /path/to/llvm/bin \
  --output out/stride-runtime
```

Full integration uses `build_wifi_net17_kernel.py --mac-phy-runtime
out/stride-runtime`. The explicit profile qualifier checks the real binding
against the retained parent, its source hashes and one-unit scope. Together
with the network startup-order fix, the signed candidate is c9c33f92…,
session5e076ea0aa1dd9cf, floor1738713600/footer0/parent3. Hardware remains
unverified until a corresponding live record exists.

See [component evidence](../../../docs/evidence/wifi-station-stride-20261120.json).
This does not establish that the observed firmware TLVs were short. Keep the
first-WMI fault and this proven memory-safety defect separate until hardware
evidence connects them.

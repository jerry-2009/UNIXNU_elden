# Original firmware cache and Linux PCI lifecycle hooks

`FirmwareCache.cpp` reads the retained stock `modem_a` through the existing
native UFS/FAT owner. The native PCIe worker now binds this cache to the same
confirmed WLAN provider/epoch, and withdraws it during stopping. It does not
embed firmware bytes in the boot image or write the modem partition.

Only these Linux request names are mapped, optionally under the exact
`ath12k/PEACH/hw2.0/` or `PEACH/hw2.0/` prefix:

| Request | Original modem file |
| --- | --- |
| `amss.bin` | `image/peach/amss20.bin` |
| `m3.bin` | `image/peach/phy_ucode20.elf` |
| `aux_ucode.bin` | `image/peach/aux_ucode20.elf` |
| `tmel.bin` | `image/tmel_peach_20.elf` |
| `regdb.bin` | `image/peach/regdb.bin` |
| `board.bin` | `image/peach/bdwlan.elf` |

The M3 selection is independently bound to this tablet's original CNSS module
by [the stock audit](../EldenPcie/TRANSPORT.md#original-firmware-evidence).
Sizes and hashes are the unchanged `package/EldenWifiFirmwareInputs.h`
manifest. `data20.msc` is not substituted for M3. Unknown files, including the
optional packed `firmware-2.bin`, return missing-file without reading storage.
No dummy calibration, MAC-address file or successful fallback is supplied.

Each file is read in at most 64 KiB chunks and fully SHA-256 checked before
publication. The six files total 7,517,874 bytes. Repeated requests reuse the
verified pointer. A known-file failure is retained without retry. Stop/epoch
withdrawal is checked between reads and before publication. Cache locks serialize
FAT state; status uses try-lock and stop does not wait for the lock. All returned
and failed-read buffers remain allocated until reset, so no speculative free
follows uncertain lower-level storage DMA.

## Executed validation

The actual cache, ModemFiles and FatVolume bodies ran against the **original
367,001,600-byte modem backup** with real SHA-256. Eight scenarios / 55 checks
cover all six files, cache hits, prefixes, allocation/read/hash failures,
IRQ misuse and cancellation while a reader holds the lock. ASan/UBSan pass.
The host substitutes kernel allocation/locks and uses CommonCrypto for SHA-256;
the native object compiles against the real kernel SHA2 and IOLock headers.

- Firmware object: `5f8bad02e98f2cd0297257df0a39a01237b73ba7606bb6a230314673df6d3338`.
- Cache/reader binding: `14f5fbda70203b54293f0df3e2c7d62310ade818221befaa812f20693854dd95`.
- Zero warnings, FP/SIMD and initializers; all FAT/UFS/SHA/lock imports exist
  in v163. The existing FAT implementation is reused, not linked twice.
- The native worker/cache combination also passed 75 modeled transport
  scenarios / 391 checks and compiled with zero warnings. Worker object
  `b66a202fad913a6e137d9ddd5b31188983a55fffc8f2564f917caeac0cb28be4`,
  12-object/binding aggregate `f863780a07b7fad9074598fdbb1297d01b8f8df37a973ecb32f1a27e9c98ed86`.
  Its 82 remaining imports all resolve in the v163 native reference.

These are offline component results. No XNU firmware transfer, hardware MHI
operation, complete new kernel or signed boot image was produced this round.

## Actual Linux consumer and master-enable sites

The optional `PciLifecyclePatch.py` derives from the exact frozen MSI-corrected
adapter. Before a matching `drv->probe`, it passes the real `&g_dev.dev` to
`elden_wifi_runtime_bind`. Failed probe and remove call the corresponding
unbind hook; a failed unbind is logged and must remain tracked by the native
owner until recovery. Duplicate remove is prevented. Subsystem and Device
Control setup now propagate I/O/readback errors before binding the consumer.

After endpoint MSI programming has actually read back, the allocation function
calls `elden_wifi_runtime_enable_master` before publishing its descriptors.
Failure propagates and attempts MSI disable; it does not claim hardware drain.
Nineteen actual-entrypoint scenarios / 111 checks pass under ASan/UBSan.

The PCI unit was rebuilt against the real frozen headers and linked with 124
unchanged objects. Its output is
`8a37dba58112261f535b28d6deb519ab5f9e5159e0e805dc60b970466f640f9b`;
the 125-object binding is
`493ea717908560fe76eabc35a1313ed9ef35912fa95b1866173873fd519a315e`.
The unit retains 24 inherited warnings; the MSI functions have none.

**The three native runtime-hook bodies and MHI execution/drain remain to be
implemented.** Their unresolved imports are deliberate, along with the real
`pwrseq_qcom_wcn_set_ol_cpr` dependency. This link is not proof that QMI is
already bound on hardware. The current native master-readiness callback still
refuses with `-95` until the real MHI stop path exists.

## Reproduce and next

```text
python tools/test_wifi_firmware_cache.py --modem <original-modem_a.bin> --output <new-host-output>
python tools/build_wifi_firmware_cache.py --clean-build <source-built-base> --reference-kernel <qualified-native> --llvm <llvm-bin> --output <new-cache-output>
python tools/test_wifi_pci_lifecycle.py --component-repository <fixed-Ath12kWifi> --output <new-pci-host>
python tools/build_wifi_pci_msi.py --native-lifecycle --runtime-build <verified-runtime> --llvm <llvm-bin> --output <new-pci-output>
```

Add `--firmware-cache-build` to the previously qualified native PCIe transport
build and `--firmware-cache` to its host test. Full `build_wifi_runtime.py` also
accepts `--native-lifecycle`; its auditor verifies the exact derivative. The
full empty-directory recipe was updated, not rerun; the targeted compile/link
and combined native checks above were executed.

Next implement the real native hook bodies, clock/poll/heap/firmware ABI wiring,
MHI start/cancellation and hardware reset/drain. The frozen Linux register
contract is `drivers/bus/mhi/common.h`: CTRL38 reset bit1, STATUS48 state15:8,
SYSERR2, READY0; RESET state0. `host/pm.c` requests reset and waits for the bit
to clear. Do not infer physical quiescence from an empty allocation count.
Then disable PCI master, drain IRQ handlers, and defer SMMU fault-IRQ shutdown
until that completes. Build/test one combined MHI candidate after qualification.

[Evidence](../../docs/evidence/wifi-firmware-cache-20261116.json). Mac outputs:
`lab/wifi-firmware-cache-20261116/{source2,host1,native1,pci-host1,pci-native1,transport-host1,transport-native1}`.
Workbench copies are in matching `edl_work` / `lab/records` directories. The
original backup is retained unchanged; the Mac test copy has its complete SHA
verified. No tablet or charging control was accessed this round. v163 remains
the latest hardware image, and charging / the whole peripheral Goal are incomplete.

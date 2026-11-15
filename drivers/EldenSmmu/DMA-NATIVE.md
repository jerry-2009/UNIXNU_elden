# Native DMA callbacks — built, not yet called by the Wi-Fi worker

The explicit `DmaNativeSource.py` variant appends the native adapter to the
qualified early SMMU owner. It retains `Native.cpp` and all mapping-only
profiles unchanged. `DmaNative.inc` connects the [arena](../EldenWifi/DMA-ARENA.md)
to the real, verified NC mapping and kernel IOLock operations. Bind requires
SMMU readiness and the exact PCIe/WLAN provider's confirmed power epoch.
One bind attempt is allowed per boot. No fixed physical address is used.

The exported allocation/free/map/sync signatures match the four plain-C DMA
callbacks in the frozen Ath12k `lx_platform` ABI. They are not registered with
that runtime yet. Allocation and mapping recheck admission while serialized;
withdrawal during zeroing prevents exposing the new buffer. The NC ordering
barrier is `dsb sy`. Invalid free/map/sync latches the first error and stops
new submissions. IRQ-context calls refuse before acquiring a sleeping lock.

`elden_wifi_dma_stop_begin()` only sets the atomic withdrawal flag. It cannot
block behind a long zeroing operation. An active/waiting callback counter and
try-lock status snapshot let the recovery worker observe progress. Existing
buffers can still be synchronized and freed during stopping. The original
IOKit backing, context tables, arena metadata and mutex stay alive until
platform reset, including failed bind attempts; no new retry/unmap path exists.
An empty arena/callback count is not a hardware MHI drain proof.

Status does not read a concurrently published owner when its acquired state
is still idle. Once the terminal bind state is acquired, fields are stable;
status reports busy while the metadata lock is held. Host models cover this
idle state, failed allocation/lock setup, stale owner/epoch, duplicate bind,
full-range validation, release errors, SMMU withdrawal, withdrawal during
allocation, IRQ misuse and a real two-thread lock/stop interleaving.

## Validation

13 scenarios / 98 checks run the actual adapter and arena under ASan/UBSan.
Only the ARM barrier is substituted; IOKit allocation/locks, SMMU memory and
power checks are explicit host models. Native compilation then uses the actual
source-built kernel headers, IOLock ABI and scalar `dsb sy` implementation.
The 12-component SMMU+arena relocatable binding resolves every kernel import
against v163. The early guard remains a real external dependency, supplied by
the UFS object in a complete kernel.

- Native object: `ccece9b8d9d4446bef1a65d7ff9329c4a2029608641d53dd4d5b386f8c34ed95`.
- Binding: `84e5a00a888be3c847f082da813ce0ba2fbe1bc2cb7569da5019c6c1a8bbd39e`.
- No FP/SIMD or initializer; one existing signedness warning in the unchanged
  SMMU status code, zero warnings in the domain/arena cores.
- Initial native1 check expected the early guard to be missing, as in v158;
  v163 already exports it. The explicit DMA variant now requires all imports
  to resolve against that newer reference. The failed report remains retained.
- Native2 preceded the idle-status race correction. Final sources are source3,
  with host2/native3 outputs. No signed image or tablet trial was produced.

```text
python tools/test_wifi_dma_native.py --output <new-host-output>
python tools/build_smmu_domain.py --clean-build <source-built-base> --memory-build <prefault-memory> --selection-build <selection> --route-build <route> --reference-kernel <v163-native.macho> --dma-arena-build <arena-build> --llvm <llvm-bin> --output <new-native-output>
```

The memory provider must explicitly report the verified prefault variant.
The older full-kernel recipe still requires its original 11 components; it
will reject this 12-component binding until a new runtime profile is reviewed.
This prevents accidentally packaging new DMA behavior as the old diagnostic.

## MSI route and next step

The exact stock FDT resolves endpoint RID `0x100` to ITS device `0x1401` at
`/soc/interrupt-controller@16000000/msi-controller@0x16040000`. Fixed TB322FC
Linux also has `msi-map`, which disables its local DesignWare iMSI receiver.
Separately, that same SM8750 DTS describes `msi0..7` as INTID173..180
(SPI141..148). Thus INTID173 is independently supported by the board source;
it is not inferred from Sheng. The stock DT itself lists global/INTx lines.

The controller receiver uses DBI `820/824/828/82c/830` and 32 vectors per group,
verified against the pinned DesignWare code. Choosing native iMSI differs from
the stock ITS configuration and remains untested. It requires explicit receiver
setup, readback, IRQ ownership and an actual device MSI result. Source facts
alone cannot establish that it works. No ITS driver was added in this work.

Next connect these callbacks from the confirmed PCIe worker, implement the
selected MSI receiver/config-error propagation, and qualify real MHI/IRQ/
completion draining within the recovery deadline. Then enable bus mastering
and start the existing MHI/Peach/QMI stack. Do not repeat a mapping-only boot.
The current stop log `dma-started=0` and old reset-only quiesce must be replaced
before device DMA is enabled; SMMU fault IRQ withdrawal must also follow the
new drain ordering.

[Evidence](../../docs/evidence/wifi-dma-native-20261116.json).
Mac: `lab/wifi-dma-native-20261116/{source3,host2,native3}`; workbench:
`edl_work/wifi-dma-native-20261116` and `lab/records/wifi-dma-native-20261116`.
No charger setting or tablet boot was changed during this work. A fresh stock
read showed 100% / 4467 mV / 25.9°C / Full / current 0 and original protection
settings, which does not complete low-SOC or dual-port charging validation.

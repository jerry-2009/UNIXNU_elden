# v161 complete page proof across descriptor segments

`SegmentSource.py` removes only the assumption that the first descriptor segment
must cover the allocation. Every4KiB physical address, contiguous expected PA,
CPU read/write PAR and cache attribute remains checked before use. Host tests
reproduce the64MiB segment boundary and still reject a real physical gap.

Hardware passed the full130MiB primary-page checks, then refused stage11/reason4:
the requested NC alias returned PAR `ff000008eb800b00` (WB0xff, expected0x44).
The backing remains owned; no SMMU programming occurred. All recovery and stock
settings restoration passed. Capture158875 bytes/reported drop0; no reconnect.

Image `a45c711e0669d719558def39e56e27e652825805535457579d93cf7df2310a50`,
session `ba8c279e5034f1db`. Add `--segmented` to the memory build and
`--segmented-memory --memory-detail` to the kernel build. Inputs and records are
under workbench `edl_work/smmu-segmented-v161-20261116` and matching live/lab folders.
[Next unique mapping fix](../smmu-unique-memory/README.md). No DMA acceptance.

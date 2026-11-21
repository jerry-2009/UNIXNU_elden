# v162 unique NC mapping

`UniqueSource.py` adds only `kIOMapUnique`, bypassing IOKit's same-task static
mapping shortcut. The actual source and mock test confirm that shortcut can
reuse the original address without applying the requested cache mode. All
physical and NC0x44 checks stay in place.

Hardware now refused stage11/reason3 with PAR0x80d: the new alias had not been
faulted into the CPU page tables. This is not a completed NC mapping or SMMU
domain. No SMMU write/IRQ registration occurred; sync return, full stock Android
and original settings restoration passed. Capture159107 bytes/reported drop0.

Image `35a16fe8549ce84cfd7869500c9533ce3506c9a42d25e3312a244a8055051ee3`,
session `aa4b42975ee7d9b0`. Use `--unique-map` for memory and
`--unique-memory --segmented-memory --memory-detail` for the kernel.
Inputs/records: workbench `edl_work/smmu-unique-v162-20261116` and matching live/lab
folders. [Next prefault stage](../smmu-prefault-memory/README.md).

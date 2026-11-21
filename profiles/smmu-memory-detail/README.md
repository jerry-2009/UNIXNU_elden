# v160 allocator diagnostics

Hardware located v159's generic-71: allocator stage6/reason2, first data segment
64MiB versus130MiB requested; table segment270336 bytes. This is an IOPL/segment
reporting boundary, not proof that later physical pages are discontinuous.
No SMMU write or fault IRQ registration occurred. Touch DMA, CPU admission,
sync return, full stock Android and original settings restoration passed.
Capture161587 bytes, reported drop56; required diagnostic/recovery lines present.

Image `37d8dbec1d0a087247e544d5228266c9f5d2deb72f15a9a1a1c87fd8a01de437`,
session `48dc8659104d159f`. [Next segment fix](../smmu-segmented-memory/README.md).
Use the existing SMMU component build with `--memory-detail`; the underlying
admission and1019-byte arguments are unchanged. Raw inputs/build evidence are
retained in the workbench `edl_work/smmu-memory-v160-20261116` and
`edl_work/live-smmu-v160-20261116`. No Wi-Fi/DMA acceptance is claimed.

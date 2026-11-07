# Original storage ABI qualification, 2026-11-06

The owned GOP candidate (SHA256
`1a4d7d81cec5305aa28a7dff46392e04cda3ea8267df9d9ba109ecbad41360fa`)
has been audited against public Darwin 23 IOStorageFamily revision
`e45fbe30a7879e0b16e26dddb78538f1b00e0bff`. The compiled annotation object
is not linked or executed. Its 190 virtual slots agree with the original
IOStorageFamily: 176 source-kernel bindings include 162 inherited methods
and 14 pure virtual slots. The real protected C2 constructor and base D2
destructor were identified through their actual source IOService thunks.
The abstract class D1/D0 entries are BRK traps and must never be called.

A bounded QEMU raw-entry run executed the unchanged candidate through the
original storage metaclass constructor. Its parent is the actual source
IOService metaclass; observed class sizes are 0x90 and 0x88. The original
kernel executed `MSR SCTLR_EL1, x0` with x0=`0x3454593d`. QEMU's 64-bit
`SCTLR` register changed to that exact value and retained it at the storage
constructor stop. This verifies the EL1 register mapping rather than
assuming an alias. TCR and TTBRs also confirm native 4 KiB translation.
This raw-entry fixture does not test UEFI, ExitBootServices or UFS I/O.

`scripts/build-elden-ufs-bindings.py` qualifies the concrete NativeUfsBlock
against all 190 slots and requires all 14 pure transport operations. It
only adds genuine original IOBlockStorageDevice imports to libShengUfs.a;
it does not replace the original class implementation with annotation
code or stubs. The audit, candidate and prelink plan must have identical
provenance. A later kernel must be checked again against its own final
prelink plan because source-kernel export addresses can move.

The explicit root-check builder now requires three absolute input paths:
`ELDEN_STORAGE_ABI_AUDIT`, `ELDEN_STORAGE_ABI_CANDIDATE` and
`ELDEN_STORAGE_ABI_PLAN`. The owner-side build runner supplies the
qualified inputs and restores the prior defconfig after building.
The driver checks actual original class registration before root probes
or allocation, in addition to compile-time parent class sizes.

The complete root-check kernel has now compiled and prelinked successfully:
52,023,296 bytes, SHA256
`07d4df1d49e0dd64acab02e84a74d452c7034acd92e5a44b0ce37d67f53e4b15`.
Its own final static and live audits pass. The unchanged kernel naturally
reaches `elden_ufs_storage_class_ready`, which returns 1 before any UFS
MMIO. Its concrete class inherits the real initialized and registered
original class. Actual probe_calls, matched and requested state words are
all 1. The concrete class size is 0xd8; its parent/service sizes remain
0x90/0x88. No storage or abstract-destructor stubs were substituted.

Two earlier late-startup AMFI panics were caused by omitted synthetic
fixture fields, not by a proved crypto ABI defect. The actual hardware
candidate ADT already has crypto-hash-method=sha2-384, osenvironment=main
and amfi-only-platform-code=1. Matching those policy fields in the QEMU
fixture lets the unchanged kernel proceed to the real UFS registration
gate. The crypto reference was not modified to hide these input failures.

READ_ONLY=1 and inherited identity SMMU admission remain mandatory. This
raw-entry run does not test UEFI/EBS or hardware UFS I/O and does not prove
a disk can be read or mounted. The entry-band signed derivative is a
separate packaging and verification step.

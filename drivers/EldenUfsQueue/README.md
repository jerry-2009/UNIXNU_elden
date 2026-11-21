# Elden multi-slot / DMA core

The v153 source-only core below is now integrated and hardware-tested in
[v155](../../profiles/ufs-queue-trial/README.md): owned IOKit allocations,
per-slot issue/await, direct DMA,32 slots and post-sync shutdown are connected.
The remainder records the original component contract and its validation scope.

## Reuse and required adaptation

`upstream/` vendors exact Git blobs from ShengUfs
`b6fe07b307eeddc5e258c9d5d4387b968a55e4e9`, with original license and SHA256s.
The complete tree equals57f031c; reverted container publication is not imported.

- RegionA/B geometry, isolated cached UTRD lines and the independent uncached
  request-list design are retained as the layout reference.
- `PrdtSource.py` extracts the actual page-coalescing `hostBuildPrds` body. It
  replaces the address provider with a template callback and adds null-output/
  virtual-overflow guards. Upstream1MiB/64 entries/256KiB per PRD are unchanged.
- `QueueCore` follows upstream bitmap allocation and FIFO handoff, adding explicit
  lease generations, cancellation and terminal stop/quarantine. It supplies
  metadata operations; the native adapter must hold one mutex and provide waits.

The upstream single-slot panic fallback can proceed with slot0 after its wait,
and its direct-DMA return path does not itself pin/retain caller memory. Those
source observations are **not claims that either failure happened on Sheng**.
Elden must not inherit a forced reuse of device-owned memory. Our core refuses
release while a lease is Issued/Quarantined, including after a stale release or
global failure. It does not free any DMA allocation itself.

## Contracts for the native adapter

1. Initialize once, from zero. Cached lists use entry stride2 with separate64B
   cache lines; a qualified independent uncached list can use stride1 and32
   slots. Respect the actual CAP.NUTRS count. No automatic reopen/reset.
2. Serialize pool operations and keep issue → doorbell publication under the
   same mutex. The IRQ path takes no pool lock; it only records/wakes like v152.
   TransferPoll still owns deadline/DB/OCS checks. `pool_complete` establishes
   memory ownership only: OCS/SCSI success and authenticated data remain separate.
3. Waiters remain alive until granted or removed. A cancellation racing a grant
   returns the granted lease. Native waiting must be bounded and wake on stop;
   panic/masked/preemption-disabled paths must refuse unsafe acquisition, never
   steal another caller's slot. The core does not implement OS scheduling.
4. Close stops new issues, removes all waiters, and permits already-issued
   commands to finish normally. Uncertain DMA marks issued slots quarantined;
   no completion hint, free bitmap or later callback may release that memory.
5. Apply the existing fresh `eldenUfsIdentity` check to the inherited SID0x60.
   `elden_ufs_dma_limit` only tightens a verified identity route to all three
   SMMU widths plus host32/64-bit addressing. It is not an SMMU validator and
   performs no register writes. Do not import upstream bank reassignment or
   unrelated Wi-Fi/display stream changes.
6. The PRDT page callback must refer to a real retained, driver-owned allocation,
   using physical segments without an IOVA mapper. Planning a list does **not**
   pin pages or extend their lifetime. The native adapter is still responsible
   for that. On any invalid/unaligned/out-of-range page or excess PRD count,
   planning fails without changing the output, allowing an owned bounce fallback.
7. Remove the current per-window single-bounce serialization only after each
   request owns its snapshot through DMA, block verification and copy. Preserve
   pinned-root authentication and existing read-only/write-window gates.

## Evidence

The host harness executes the actual core and exact upstream layout. It covers
1..32 slot capacities/entry strides, non-FIFO bypass refusal, head/middle/tail
cancellation, late grant, stale/wrong-pool lease, stop/drain, fatal quarantine,
generation exhaustion,3200 leases from16 concurrent callers under the required
mutex,4096 width combinations and4096 differential PRDT plans against the
unmodified upstream function. It does not emulate a controller or native waits.

8276 reported cases pass ASan/UBSan. ARM64/iOS17 objects compile with `-Werror`,
zero warnings, no FP/SIMD, no automatic initializer, and ten expected C exports.
QueueCore has no imports; DmaPlan only imports the already-available `bzero`.

| Object | SHA256 |
| --- | --- |
| QueueCore.o | 32dce56ebcf0fdf30c0e1a6936f411230f24f23fde5bf0f9efa036c09c945e45 |
| DmaPlan.o | 58e1f4ca6292f9affe1764793484e3f5bb5ddbbc0b81efcbb651c08109178465 |

```sh
python3 tools/test_ufs_queue.py --cxx /usr/bin/clang++ --output NEW_HOST_DIR
python3 tools/build_ufs_queue_core.py --llvm /path/to/llvm/bin \
  --reference-native /path/to/verified/native.macho --output NEW_NATIVE_DIR
```

The reference native image checks dependencies only. These commands neither
link nor flash a kernel. [Validation](../../docs/evidence/ufs-queue-core.json)
records source identities. Workbench: `lab/records/ufs-queue-v153-20261115`.
Mac final: `isolated/ufs-queue-core-v153-final`.

## Integration completed in v155

The integration plan was to connect this core to owned IOMemoryDescriptor allocations, request-list cache
mapping/readback, the actual NativeUfs issue/await path, per-slot diagnostics and
shutdown. The old global diagnostic `residual` must not participate in concurrent
response decisions. Then integrate per-request snapshots/pipeline, perform full
native/Apple/entry/AVB checks, and one known-data QD1/8/32 comparison with recovery.
Those steps are now recorded in the v155 profile; sustained stress and actual
user-visible latency are separate unfinished validation.
Do not repeat component-only or v152 IRQ-only device trials.

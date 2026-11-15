# v155: 32-slot UFS and owned direct DMA

The complete native kernel, entry/boot audit and hardware trial passed. The
driver now has32 command slots, an independently mapped uncached request list,
per-slot command/response state and retained driver-owned direct-DMA snapshots.
It preserves the inherited SID0x60 identity mapping and read-only root policy.

## Hardware result and limits

Both original images passed full pinned SHA256 verification before publication.
The QD trial then completed48 batch records /1536 direct commands, with matching
hashes across QD1/8/32 for16 equal datasets. Each group has four batches of32
reads. Real doorbell observations reached9 outstanding4KiB commands and27
outstanding128KiB commands;32 is the configured slot capacity, not a claim that
32 hardware operations remained outstanding simultaneously.

| Window / read | QD1 MiB/s | QD8 MiB/s | QD32 MiB/s |
| --- | ---: | ---: | ---: |
| OS4KiB | 40.6 | 219.9 | 285.1 |
| OS128KiB | 624.3 | 1922.9 | 2836.8 |
| SystemOS4KiB | 43.2 | 203.3 | 283.6 |
| SystemOS128KiB | 655.4 | 1659.3 | 2430.3 |

These numbers time driver issue/await only, excluding hashing/logging. Queue
depths run in fixed1→8→32 order per dataset and device cache is not controlled.
The observed3.7–7.0x QD32/QD1 ratios therefore are **not isolated causal speedups**,
filesystem throughput, CPU savings or GUI acceleration. Counterbalanced/cache
controlled comparison and sustained workloads remain future validation when
needed; do not repeat this successful trial merely to add another sample.

The list mapping reported read/write PAR `44000008eb412b00`, matching physical
`8eb412000` and Normal Non-cacheable attribute44. The inherited DMA bound is
`1000000000` (64GiB). Controller capacity/readback and the qualified mapping give
32 slots with one32-byte UTRD per entry; cached fallback retains isolated64-byte
lines and fewer slots.

Whole session:409459 completed waits,382385 completion IRQs,2547 sleeps/wakes,
zero wait timeouts/other wakes/spurious IRQs. Capture3185070B/drop155; all48
critical records and hashes were complete, with no reconnect. Root disk5s1,
early watchdog adoption/eight-core work/timer/IPI ff, and software Home to the
existing desktop passed. White widgets remain; no real-finger/GUI latency claim.
Tail10 published battery samples at high SOC had median−36mA, not proof of net
charging or energy savings against unmatched prior workloads.

Session-bound sync/reset returned to physical fastboot. Full stock SHA256
`8b8e72dad85a65d3bf6fc2c6b2a88064d0487e4696ae578e9fd4c46a33565890`,
Android/root/green/boot completion and original charging settings were verified;
sleep requested, all jobs ended.

Candidate SHA256: `09593eb8c91c6eb19737f1b12f183a3464574c8fa4f7a06450d4e72d8a7208fb`

Session `a732f97a107ffb0c`; rollback1738713600/footer0/parent3 unchanged.

## v154 refusal and correction

The first image qualified only16 slots, passed the full image pins and initial
QD1/8 matched reads, then deliberately refused the requested QD32 test. It did
not publish root. The180-second panic route and full stock recovery worked.

The imported allocation wrapper had omitted upstream's cache option when
allocating the request-list page, passing it only at mapping time. Actual OS17
IOBufferMemoryDescriptor source sets page alignment and memory-entry cache mode
from the allocation flags. v155 passes `kIOMapWriteCombineCache` at allocation
as upstream does, while keeping the PAR/address checks. Original v154 PAR was
not logged, so the exact failed subcheck is not independently established.
The source/API model reproduces the omission's fallback; v155 hardware proves
that the corrected allocation obtains the requested mapping and32 slots.
The failed image and raw logs remain in the workbench.

## Integration details

- `NativeSource.py` derives the pinned upstream queue methods and the qualified
  Elden v152 wait/early-watchdog path. MCQ refusal, firmware-outstanding checks,
  UIC wake, SMMU identity validation and all existing root pins remain.
- Real IOKit allocations back regionA/B and the separate request list. Snapshots
  are prepared, registered and retained for platform lifetime, including failed
  DMA. Unregistered caller memory takes an owned bounce path. There is no freed
  caller buffer that a timed-out controller may still write.
- Generation-checked FIFO leases guard issue→doorbell under one short mutex.
  Every slot has its own diagnostics; global residual/status fields do not decide
  another command's result. IRQ checks OCS before consuming an outstanding bit,
  covering a peer interrupt between software publication and doorbell write.
- Each root window has four independently owned snapshots through verify/copy;
  a whole-window lock no longer serializes every transfer. Whole-image pinning
  uses a prepared1MiB scratch buffer. Hash tables remain protected, fully resident.
- Pre-sync shutdown disables completion IRQs but preserves polling reads.
  The final post-sync halt closes new submissions without locks or freeing DMA
  memory in halt context. No reset/cancel or BUSY/TASK_SET_FULL retry is added.
  Long-running pressure and transient-status policy remain unqualified.

Host evidence:8276 queue/PRDT cases,17 actual native allocator/IRQ/command/snapshot
cases plus the old-cache reproduction,2305 batch sequencing/failure cases and12
real-capture mutation rejections. Hardware/page tables/IOKit scheduling are
modeled in host tests, distinct from the trial above. Full native compilation
changes one UFS object; other archive/core members, initializer targets and30
original Apple execution regions are retained.26 existing warnings remain;
the two introduced narrowing/shadow warnings were corrected before hardware.

## Reproduction and next work

```sh
python3 tools/build_clean.py --variant bluetooth --bt-exit-stack \
  --software-keystore --bluetool-launch --bt-transport-trace \
  --bluetool-lifecycle --bt-registry --bt-helper-trace --bt-process-lifetime \
  --bt-address17 --ufs-queue-trial --inputs inputs.json --output NEW --target boot --jobs 4
```

The explicit option is part of resume identity and builds all prerequisites from
source. Individual full stages/entry/pack/audit ran; the newest combined command
has not been rerun from an empty output. No historical v99 binary is required.
Staged builds use `build_charge_verification.py --ufs-queue-trial` over the verified
v152 parent. [Validation](validation.json) and [hardware](hardware.json) bind inputs.

Mac final: isolated/ufs-queue-v155. Workbench: edl_work/ufs-queue-v155-20261115,
edl_work/live-ufs-queue-v155-20261115 and lab/records/ufs-queue-native-v155-20261115.
v154 material is separate. Use the verified driver as the next Wi-Fi candidate's
base; remove the diagnostic batch call in that next build rather than rerunning
it on every unrelated feature. Charging/endurance, wireless, persistent Data,
memory/lifecycle and the full peripheral Goal remain incomplete. GPU work stays
in the owner's separate worktree until an explicit commit handover.

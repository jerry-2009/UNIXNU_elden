# v152: UFS completion IRQ and paired reads

The full kernel, entry/boot audit and one hardware trial passed. This promotes
the v151 IRQ/wait foundation to actual Elden evidence, **not a storage speedup**.
UFS remains single-slot with the existing DMA buffer and read-only root.

## Measured result

Both original images passed their full pinned SHA256 verification before this
trial: OS5796MiB and SystemOS3150MiB. Their protected per-block hashes then
verified every test read.64 paired hashes/128 rows passed, with one completion
IRQ per row. Five tested reads slept and woke on IRQ; none timed out.

| Window / read | Poll median | Hybrid median | Poll p95 | Hybrid p95 |
| --- | ---: | ---: | ---: | ---: |
| OS4KiB | 94.38us | 96.25us | 112.50us | 162.19us |
| OS128KiB | 192.71us | 201.80us | 277.55us | 280.99us |
| SystemOS4KiB | 71.88us | 68.57us | 116.41us | 120.16us |
| SystemOS128KiB | 203.85us | 204.74us | 229.48us | 216.30us |

Each group has16 samples; p95 uses nearest rank and is the maximum at this sample
count. These are warm pre-publication QD1 reads, timed around transport and copy
only. Both modes retain IRQ delivery. Hashing/logging are outside the timing;
there is no cache flush, sustained-throughput, CPU-utilization or GUI-latency
measurement. The results do not justify retuning the200us threshold or claiming
that this change solves the UI performance problem.

Entire-session counters:402717 commands,402687 completion IRQs,2114 sleeps and
2114 IRQ wakes,0 timeout/other wakes,6 spurious interrupts. Wait duration20744741us
is accumulated command wait, not consumed CPU time. The retained128 measured
rows, full pin markers and shutdown line were complete despite26 dropped bytes
elsewhere in the3129911-byte capture; no reconnect occurred.

Early ARM → trial → BSD root disk5s1 → SMP_ADOPT and eight-core work/timer/IPI ff
passed. Software Home reached the existing desktop with white placeholders
(frame4 visually checked); no physical-touch or complete graphical acceptance.
Typed sync/reset returned to physical fastboot, followed by full-SHA stock
restoration, Android/root/green/boot confirmation and sleep request. Original
charging enable/normal/EU settings remained1/095100/095100. All jobs ended.

Candidate SHA256: `024af75cd765ec6df03a049fa4481e870bc2194b86ec0a0550cb55ee8bf9c8bf`

Session: `378d8820a127a7c6`. Rollback1738713600/footer0/parent3 unchanged.

## Implementation and reproduction

`TrialSource.py` derives the already-reviewed wait source and adds a separate
read-only test after both window identities are sealed, before publication.
The exact `UfsReadTrial.h` loop alternates pair order over16 known offsets,
4KiB/128KiB sizes, after four warmups/window; each window has a10s limit.
Polling override is restored on every loop exit. An error rejects publication;
the existing watchdog/SDAM return remains. No external address input or new
write operation is provided.

330 actual-function ASan/UBSan scenarios passed, including51 wait/SPI cases
and279 read-loop read/verify/stop/deadline failures.11 real-capture mutation
checks reject omitted/duplicated/reordered rows, changed data, polling sleeps
and missing pin proof. Menu comparison retains all v150 arguments,1023 bytes,
fallbacks and vdog3; only the title identifies the new candidate. The existing
two boot tests and10 governor/menu-binding regressions also passed.

Two native objects are rebuilt: ArmCpu and UFS. The actual parent ArmCpu archive
member matches its original source-built capture. Other archive/core members,
initializer targets, scalar code and30 original Apple execution ranges are
retained. UFS26 warnings match v150 source expressions/diagnostics; CPU2 original
signedness warnings remain. No new warning is suppressed.

From a clone and declared original inputs, append `--bt-address17 --ufs-wait-trial`
to the native17 lifecycle chain:

```sh
python3 tools/build_clean.py --variant bluetooth --bt-exit-stack \
  --software-keystore --bluetool-launch --bt-transport-trace \
  --bluetool-lifecycle --bt-registry --bt-helper-trace --bt-process-lifetime \
  --bt-address17 --ufs-wait-trial --inputs inputs.json --output NEW --target boot --jobs 4
```

This automatically includes verification, OEM window handoff, backlight/PD,
CPU observation, storage-medium and the early guard. Resume identity includes
the trial option. The individual full stages/entry/pack/audit ran; this newest
combined empty-directory command has not been rerun. Staged builds use
`build_charge_verification.py --ufs-wait-trial` with the source-built baseline
and qualified early-storage parent. No historical v99 binary input is added.

[Validation](validation.json), [hardware evidence](hardware.json) and
[the wait component](../../drivers/EldenUfsWait/README.md) retain exact scope.
Mac final: isolated/ufs-wait-v152. Workbench: edl_work/ufs-wait-v152-20261115,
edl_work/live-ufs-wait-v152-20261115 and lab/records/ufs-wait-v152-20261115.

## Next

Continue upstream multi-slot/independent request-list/direct-DMA adaptation,
preserving the Elden takeover, address limits, timeout quarantine and write
gates. The current pinned-root implementation already keeps the whole derived
block-hash table in protected RAM; a new page cache adds no avoided table I/O
here. Do not repeat this IRQ-only trial to manufacture progress. Charging/net
power/endurance, wireless and other peripheral requirements remain incomplete.

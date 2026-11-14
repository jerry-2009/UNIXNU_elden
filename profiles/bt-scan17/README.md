# v133 standard extended scanning on iPadOS17

Hardware result: this candidate still sent0x200b/status0xc and then exited,
with H4 out50/up49. It is not a successful scanning baseline. The subsequent
[scan-ready17](../bt-scan-ready17/README.md) profile refreshes the dynamic
capability after successful HCI discovery, covering an ordering absent from
the isolated getter/setter checks. Full stock restoration passed.

v132 initialized HCI and published On, then the real controller rejected
LE Read Advertising Channel Tx Power0x2007 and LE Set Scan Parameters0x200b
with status0x0c. Its native scan callback propagated the error to process exit.
Sheng's proven QcaBluetooth22ff97f93416452335bb61badb14c762da653487 documents
the same prohibition on mixing extended advertising and legacy scanning.

This profile follows that policy with independently mapped21H461 addresses.
The original type0 constructor installs vtable0x1008db430; slot0x778 targets
the extended-scan getter0x1002d5cbc. Its old chip-type predicate is replaced
with actual Supported Commands byte37 bits5/6 (descriptors0xd7/0xd8 name
0x2041/0x2042). Both commands must be advertised. The getter stays read-only.
The HCI setter0x100216f34 derives the same boolean, updates the upper cache
0x10093e8b0 and original lower flag0x10093c32d. The Apple vendor-extension
setter0x100216ee0 writes false to0x10093c32e, preserving standard HCI scanning.

The unmodified selector at0x10006771c reads this lower flag and chooses the
native extended/legacy branch. Original replies, errors, scan payloads and
completion callbacks are untouched. All256 bitmap values, getter/setter,
cache publication, native selector and vendor-extension disable pass1540
instruction cases at two slides. No controller is emulated by these checks.

The adapter needs38 exact-original page rules. Only this profile replaces
the frozen parser's32-entry limit with40; each rule remains at most16 bytes,
same-page, exact name/original bytes and daemon identity guarded. Actual parser
and init bodies pass old32/new40 ASan/UBSan boundary and malformed-field tests.
The accepted native completion also resets failed_starts, restoring the old
stack_ready success behavior; rejected/unmatched completions preserve it.
Actual completion/marker host tests cover that distinction.

Two native and two core units are rebuilt from the source-built process-lifetime
parent. Other members,30 original Apple regions, entry, firmware/cache/trust,
floor1738713600/footer0/parent3 and automatic stock recovery remain checked.
Select `--bt-scan17` with the full process-lifetime chain in build_clean:

```sh
python3 tools/build_clean.py --inputs /path/to/inputs.json --output /path/to/new-build \
  --variant bluetooth --bt-exit-stack --software-keystore --bluetool-launch \
  --bt-transport-trace --bluetool-lifecycle --bt-registry --bt-helper-trace \
  --bt-process-lifetime --bt-scan17
```

Do not also select `--bt-optional17` or `--bt-complete17`; their behavior is
included. All source stages have executed individually; this combined new
option has not been repeated from an empty output. Hardware results remain
separate from source/host checks. Discovery and pairing require real evidence.

Address follow-up: unlike an assumed generic mapping, the inspected17 normal
refresh still queues0x2005 at0x10020ec18. The non-resolvable fallback branches
from0x10020edf0 directly to the epilogue; native completion0x1002112e8 clears
the busy flag. Those paths are not changed here and no current runtime cause
is claimed. Do not copy27's offsets or bypass its real address errors.

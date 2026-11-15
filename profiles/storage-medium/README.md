# v149 storage medium classification

Real iPadOS17 now recognizes the current UFS windows and RAM Data as nonrotating.
The property helper read back solid=1 for RAM536870912B and UFS3303014400B /
6077546496B. The existing kernel's DKIOCISSOLIDSTATE path then recorded isssd=1
twice for each BSD unit0/2/4 (masks0x3/0xc/0x30). The v146 baseline had zeros for
the same units. BSD root remains disk5s1. No new probe or media writes were added.

This was built over the fixed-frequency v146 observation/PD kernel; v148's
experimental governor is not selected. Boot arguments and all other assets are
identical to that baseline apart from the derived session. The two changed
objects retain all exports and initializer targets; other archive/core members,
the original Apple30 executable ranges, entry and AVB checks pass. UFS still uses
the original single-slot polling transport, and RAM seed memory is not freed.

Image `37dcfc68146ce21991bdfc5f531eeae493ccfedcfe279dd3abc4b5d10a8e345b`,
session `33ebd0d127500e65`, rollback1738713600/footer0/parent3,6GiB. The helper's10
ASan/UBSan cases and complete native/entry/pack/audit stages passed. UFS has26
existing warnings and RAM0; no warning override was added. New IOStorageFamily
reference HEAD7edb88fb is inventoried for later syncing, not used as a replacement
binary family.

Capture3616844B/drop132, no reconnect/discontinuity. Three property publications
and all six SSD log records are complete. PD and root remained available; typed
sync/reset reached physical fastboot, full-SHA stock8b8e72da was restored, and
Android/root/green/boot/charging-setting equality passed; sleep requested.

Frame7 visually shows the desktop, with the existing white widgets. Earlier
frames show the app library/search. The touch driver reported119 input reports;
whether these came from a person's finger is unconfirmed and is not counted as
physical-touch acceptance. The automatic template matcher did not accept the
desktop and requested its bounded return; original trial.json is preserved.

The first32 display-copy samples have median133.41ms, comparable in magnitude to
the previous134ms records. The last10 published battery samples have median−82mA,
still discharge. Different startup/UI/input phases prevent attributing those
numbers to the medium change. No throughput/latency multiplier or power saving,
full protection cycle, persistent RAM storage or separately read mount flag is
claimed. [hardware.json](hardware.json) retains the limits and losses.

## Reproduction

Add `--storage-medium` to the documented native17 charging option chain for
`tools/build_clean.py`; omit explicit `--cpu-governor`, `--cpu-power-observation`
and `--pd-gui`. Prerequisite stages lead to the unchanged v146 native parent.
Direct staged builds use `build_charge_verification.py --storage-medium` with
the usual clean-build/parent-build/original-kernelcache/llvm/output arguments.
The new helper handles current-unit UFS and base-native RAM compile contexts,
with SHA-bound source overrides. The individual full stages ran; the newest
combined empty-directory command was not repeated.

Source/host/source-semantics records: [validation.json](validation.json) and
[semantics.json](semantics.json). Final Mac build is isolated/storage-medium-v149;
workbench edl_work and lab/records use storage-medium-v149-20261115, and the live
capture uses live-storage-medium-v149-20261115. No jobs remain active.

# Full Peach Wi-Fi C runtime — compiled offline

Current QMI follow-up (2026-11-15): [QMI-POWER.md](QMI-POWER.md) supplies the real
external power callback and consumer binding API. A separate128-object
relocatable link resolves it against the unchanged125-object runtime and
native/shared WCN providers. The historical report below remains unchanged;
the native PCIe/MHI caller, whole kernel and hardware are still unverified.

All125 production C objects now build from the pinned Ath12kWifi5f7f5a8 sources
plus the explicit TB322FC Peach backport. The complete official preparation flow
is applied: Linux/mac80211/cfg80211 sources, MHI hooks, completion/workqueue
adaptation, crypto and generated notification/validation functions.

The final build ran from a new directory using `build_wifi_runtime.py`. The
first attempt's missing generated pwrseq header was corrected in the maintained
recipe; the later complete build requires no manual header injection.

This initial report uses commit `eac20d1b76c9d809895910bfc702f218ac1e3a47`.
Current builds also include the [MHI status-read repair](peach/MHI-STATUS-READ.md);
its complete rebuild and comparison are separate records.

## Evidence and remaining integration

- 125 ordinary ARM64/iOS17 objects, scalar instructions, no automatic initializers.
- 456 distinct consumed compile inputs match their recorded hashes.
- The original sheng symbol-prefix policy is applied. Renaming preserves loaded
  code/data and symbol bindings; no duplicate definitions remain.
- 14 external symbols remain:13 resolve in the v100 reference kernel; the
  unresolved `pwrseq_qcom_wcn_set_ol_cpr` is the real native WLAN power dependency.
- The three previously checked Peach QMI flow bodies remain unchanged after the
  complete upstream preparation flow.

This is a complete **C stack object build**, not a linked boot kernel or a
networking result. PCIe/BAR/MSI/DMA/firmware and native network/control endpoints
are provided by board callbacks and still need implementation/integration.
The native WLAN power provider must serialize the shared WCN resources and
return real execution errors. The BT acquire flow is not a WLAN start function.
No fake success implementation or fallback was inserted for the missing symbol.

The initial compiler run produced9,334 warnings, preserved in the object logs.33 distinct
source positions concern potentially uninitialized variables or incompatible
pointers; the full warning review remains open. Those warnings are not waived by
the successful build or host tests. See the categories and limits in
[the evidence record](../../docs/evidence/wifi-runtime-20261113.json).

## Host lifecycle result

The official mainline-runtime fixture passes under ASan/UBSan after correcting
two outdated **test callbacks**: `config` and `set_rts_threshold` require the
Linux7.0 `int radio_idx` argument. The original fixture failed UBSan's indirect
function-type check. The failure is retained. Exact pointer-type static asserts
now verify both corrected prototypes; existing fixture assertions are unchanged.

The fixture covers original cfg80211/mac80211 lifecycle, radio off/on, TX
ownership/bounds/epoch, progress while the wiphy lock is held, nonlinear RX,
CQM notification encoding, stale-event rejection and teardown. Radio operations
are simulated; real ath12k/MHI/QMI transport and power are outside that fixture.
Its76 compiled host objects share261 exact input files with the final native
build. No tablet was accessed and no wireless association was performed.

## Reproducibility and generated outputs

The full Linux export is pinned by `peach/runtime-linux-input.json`; all7281
exported entries were checked against raw Git blobs with EOL conversion disabled.
Inputs are the official Linux7.0.14 tree, fixed Ath12kWifi and sheng Git commits,
the prior Peach source snapshot and the original verified supplicant2.12 archive.
FreeBSD is not consumed by this build and is not fetched for it.

The original generators run in a dedicated new directory. Their file retirement
is redirected to a private macOS `.Trash` subdirectory with planned/moved
receipts.17 generated entries were moved and verified. The retirement helper's
file/directory/symlink cases and rejection of outside/root paths also passed.
It does not empty Trash. Source snapshots, failed builds and logs remain recorded.

From the authoritative repository, Python3.12 and macOS/Xcode:

```sh
python3 tools/export_wifi_linux.py --scope runtime \
  --repository /path/to/linux-ath12k-7.0.14 --output /path/to/linux-export
python3 tools/build_wifi_runtime.py \
  --component-repository /path/to/Ath12kWifi --board-repository /path/to/UniXNU-sheng \
  --linux-archive /path/to/linux-export/linux.tar.gz \
  --supplicant-archive /path/to/wpa_supplicant-2.12.tar.gz \
  --backport /path/to/prepared-peach --llvm /path/to/llvm/bin \
  --kernel-reference /path/to/verified-v100/native.macho --output /path/to/new-runtime
python3 tools/audit_wifi_runtime.py --build /path/to/new-runtime \
  --llvm /path/to/llvm/bin --kernel-reference /path/to/verified-v100/native.macho \
  --output /path/to/new-runtime/independent-audit.json
python3 tools/test_wifi_runtime.py --build /path/to/new-runtime
```

Use a new output for each build. The `--resume-fixture-abi` option exists only
to resume the exact recorded pre-fix fixture failure; ordinary new tests apply
the signature corrections before their first compile. Compiler and linker tools
do not install anything on the tablet.

Final Mac build: project-local `lab/wifi-runtime-20261113/complete`. Initial
build and host fixture: `lab/wifi-runtime-20261113/build`. Windows evidence and
verified object copies: workbench `edl_work/wifi-runtime-20261113` and
`lab/records/wifi-runtime-20261113`. Existing signed candidates remain unchanged.
The full peripheral Goal, including charging/real touch/WLAN, is still active.

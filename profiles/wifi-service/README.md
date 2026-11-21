# v174 real Wi-Fi service assets

This profile installs the already source-built arm64/iOS17 supplicant and adds
its upstream launchd job. It preserves all 561 existing jobs, other cache entries,
and previous trust modules; exactly two trust entries are added for the helper
and replacement cache. Credentials are not included.

Only qualified volatile RAM Data is written. Exclusive/no-follow creation,
same-mount checks, exact bytes, owner/mode, fsync and close results are checked.
The executable is exposed through a read-only union at `/usr/libexec`; config is
mode0600. Failure never publishes ready and rollback refuses a different overlay.
`ewt=1` admits this staging without enabling the Bluetooth hardware worker.

The private factory `Intf0MacAddress` is read from the original Android persist
file using `tools/device/export_wifi_mac.py`. It stays outside Git. The build
revalidates original/canonical/header agreement and pins private input hashes.
Only `wlan_mac.bin` gets this file; all other firmware requests use the existing
verified cache. Runtime/epoch/stop admission remains required.

## Rebuild

Use the source-produced v173 output described in
[the physical-fence profile](../wifi-platform-fence/README.md), the current
`build_bt_address17.py` core output, the clean XNU SDK, and the arm64/iOS17 helper
from `tools/build_elden_wifi_userspace.py`. No proprietary executable, generated
header or device identifier is distributed in this repository.

1. `build_wifi_service_assets.py --base-runtime <v173>/runtime --userland <helper-build> --output <assets>`
2. `build_wifi_service_core.py --core-build <address-build> --clean-build <clean> --service-assets <assets> --llvm <llvm> --output <core>`
3. `build_wifi_service_native.py --parent-native <v173-native> --clean-build <clean> --service-core <core> --factory-mac <private-export> --reference-kernel <v173>/native.macho --llvm <llvm> --output <native>`
4. `build_wifi_service_kernel.py --parent-build <v173> --service-core <core> --service-native <native> --service-assets <assets> --clean-build <clean> --original-kernelcache <21H461-original> --output <kernel>`
5. Use `prepare_v91_entry.py`, then `build_v91_boot.py` and `audit_v91_boot.py`
   with `--wcn-report <kernel>/result.json --bt-runtime <kernel>/runtime` and the
   original signing/floor inputs. `assets-contract.json` and
   `native-contract.json` qualify this exact profile.

These are incremental source build steps over regenerated parent outputs, not a
claim that an empty-directory current-profile command includes this extension.
Preserve the published source revision for v174; later profile inputs must not
be used to overwrite its fingerprints.

## Validation and actual result

44 complete staging tests / 28 VFS failure sites,19 actual MAC-adapter cases and
11 asset qualification cases pass. VFS, platform state and faults are modeled;
the host tests do not establish live mounts or firmware behavior. The old v173
qualification also passes using the new dispatcher. One core and one native
object changed; the other linked inputs, 30 Apple executable regions and7124-byte
entry/return contract remain verified. Core retains91 warnings, native1; neither
is described as warning-free.

Hardware confirms assets stage5/status0, signed cache stage5/status0, ready1,
factory MAC supplied, and real firmware stage4/error0. **The service has not
started**: AMFI rejects the exact helper with launch constraint
`c[8]p[1]m[1]e[6]`. No control connection or real scan result is accepted; BSS0.
Next adapt the existing narrowly scoped RAM-overlay owner-launch rule to this
exact signed helper, then test its connection and scanning. The BSD/IOKit network
bridge, association, DHCP, traffic and UI are still outstanding.

Physical fence/BM-off/transactions-sampled+idle/MSI-stop/PERST-low/WLAN-stop,
session-bound reset, actual fastboot and full stock restoration pass again.
MHI warm reset remains unverified. Android/root/green, original charging/radio/
scan settings and sleep request are restored; no supervisor remains.
[Evidence](../../docs/evidence/wifi-service-v174-20261116.json).

# Complete SM8750 station candidate

This follows the actual hardware-accepted portable Y700 scan. It imports the
same fixed Piano donor's station/authentication/association, REO/TCL/WBM data
path, ordered keys and WPA2-Personal userspace helper. Its public iPadOS17
network interface uses our already-qualified Sheng bridge. This is a signed
test candidate; association/DHCP/network traffic have not yet been accepted.

The fixed donor commit is `2438556c77c90c22c7b76e57eb8b40c44b35f1af`.
`upstream/source.json` records each imported Git blob and BSD license. No
Piano voltage, GPIO, SMMU, firmware, macOS27 user client or framework ABI is
copied. The factory Y700 firmware/PCIe/DMA/return code remains in force.

`Station.cpp` runs the original `WifiSta.h` ladder after the actual scan:
station parameters, real peer creation/map, reorder queues, VDEV start,
authentication/association, peer association, VDEV up, then controlled-port
authorization only after genuine key completions. It uses the donor's
`WifiDp.h` rings and receive selection, software-ring1 refill and EAPOL path.
Key index/VDEV/generation are checked. The first diagnostic profile is
immutable for this boot. No failed/disconnected association remains a
usable BSD link. Keys/profile/outboxes are wiped when their lifetime ends.

The portable protocol state is in BSS and large transmit queues are explicitly
zero-initialized; no C++ global constructor or SIMD is admitted. Socket and
ifnet callbacks only copy/enqueue requests under a short lock; all register
access and protocol progress occur on the original worker.

`StationPortNative.inc` exposes one privileged `org.unixnu.elden.wifi.8021x`
client. The unchanged donor helper implements PBKDF2/HMAC/AES-key-wrap using
the system CommonCrypto C interface, verifies replay/MIC/RSN and handles group
rekey. Its adaptation changes the control name/path/branding only. A fresh
root-only owner-profile input can be exported from the currently connected
Android network using `tools/device/export_wifi_profile.py`; it never prints
credentials and stores them outside this repository. Generated profile/binary
inputs are private and are not published in Git.

The original launchd staging path carries the helper at the existing verified
vnode path, with an exact new CodeDirectory hash and signed cache/trust entries.
The narrow helper-owner predicate changes only that exact digest. Other561
jobs and all original trust modules remain. Only one kern_exec object is
rebuilt for these assets. No blanket executable whitelist is introduced.

Build entry points accept explicit prepared/clean input directories:

```text
python tools/build_wifi_station_assets.py --base-runtime SCAN_RUNTIME_ASSETS --clang CLANG --output NEW_ASSETS
python tools/build_wifi_station_runtime.py --runtime-build ORIGINAL_125_OBJECT_BUILD --parent-build TESTED_SCAN_RUNTIME --llvm LLVM_BIN --output NEW_RUNTIME
python tools/build_wifi_station_native.py --parent-build TESTED_SCAN_WORKER --profile-header PRIVATE_HEADER --runtime-build NEW_RUNTIME --clean-build CLEAN --llvm LLVM_BIN --output NEW_WORKER
python tools/build_wifi_station_core.py --parent-kernel TESTED_SCAN_KERNEL --assets NEW_ASSETS --clean-build CLEAN --llvm LLVM_BIN --output NEW_CORE
python tools/build_wifi_station_kernel.py --parent-build TESTED_SCAN_KERNEL --runtime-build NEW_RUNTIME --native-build NEW_WORKER --core-build NEW_CORE --assets NEW_ASSETS --clean-build CLEAN --original-kernelcache ORIGINAL_21H461 --output NEW_KERNEL
python tools/test_wifi_station_qualification.py --report NEW_KERNEL/result.json --output NEW_QUALIFICATION.json
```

The donor's original assoc/sta/dp/net tests and helper crypto/replay/group-rekey
self-test pass ASan/UBSan. `TestStation.cpp` executes our real owner/profile/
generation/port/queue refusal code; modeled memory is not hardware success.
Complete native/prelink,30 original Apple executable hashes, entry delta7124,
12 composition mutations, original recovery/menu limits and signed package
audit pass. Original C warnings157/152/83/67, worker1 shadow, core91 warnings
remain; station scalar C++ compiles with `-Wall -Wextra -Werror`.

Candidate `87d1c43cce7d15a45794a8388948e59094209d95c924a746cfcb4410aeb4b915`,
session `2661d591ea5855d4`, floor1738713600/footer0/parent3 is not yet tested.
Mac `lab/wifi-portable-station-20261120/{assets3,runtime4,native3,core1,kernel3,entry1,package1}`;
workbench `edl_work/wifi-portable-station-20261120`. Failed build attempts are
retained separately, with no device writes from them.

The next trial checks the whole chain once: real VDEV/auth/association, WPA2
key completions and authorization, BSD RX/TX, DHCP/traffic, then bounded
protocol teardown and actual BM/transaction/MSI/PERST fence, physical fastboot,
full stock/root/green/original-setting restoration. A stage or queued request
alone does not satisfy those gates. Full peripheral Goal stays active.

## First full hardware result

The real Y700 scan, VDEV start, authentication and association passed. The
iPadOS17 network bridge started at stage4 and the exact signed helper launched.
Three EAPOL frames were received; three transmit descriptors were submitted,
but no TCL/WBM transmit completion was observed. Keys0/port closed: WPA2,
DHCP and usable data traffic remain unaccepted. Submission is not an RF ACK.
Protocol drain timed out; actual BM-off/transaction-idle/MSI4/PERST-low,
typed physical fastboot/full stock/root/green/original-setting restoration
passed independently. See [hardware evidence](../../../../docs/evidence/wifi-portable-station-hardware-20261121.json).
Next compare the successful donor's TCL/WBM/peer setup before more hardware.

## Current OEM command adaptation

The consolidated TX trial proves TCL consumption3, WBM completion0 and
status0/configured1 from the real mode response. HIF lifetime is already
accepted. The loaded OEM has newer VDEV_START/UP and PEER_ASSOC envelopes;
the prepared [OEM wire adaptation](OEM-WIRE.md) adds only their proven
lengths and disabled non-MLO tails. The real peer-association confirmation
now returns in21ms; helper message2 is generated, but TX/WBM completion0
and WPA2/DHCP/traffic remain unaccepted. Old donor blobs and
older candidate/result hashes remain unchanged.

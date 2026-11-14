# v128 Bluetooth registry publication

Sheng publishes both /arm-io/bluetooth and a named IOService under the platform
expert. Elden previously had an IOResources child and chosen address only. This
candidate adds four ADT properties (name, device_type, encoding1, speed8000000),
publishes the verified hardware address in the DT node and service, adds the
service device_type, and uses IOService::getPlatform. The speed is Elden's actual
configured8Mbaud, not Sheng's3.2Mbaud. No reg/IRQ or hardware identity is invented.

Publication rejects missing/malformed/mismatched DT transport metadata. On
withdrawal it restores the old address only while the node still holds the
owner's property, preserving a replacement by another owner. The existing
kernel control protocol, HCI/UART/power/shutdown code is otherwise unchanged.

The actual publish/retract functions pass19 ASan/UBSan registry-double cases:
missing node, wrong values/types/length, absent provider, init/attach/start and
each property failure, success, restoration and foreign-property preservation.
This is not an IOKit/hardware test. Native compilation uses the original17
IOPlatformExpert header already in the closed overlay. One BT archive member
changes; core inputs, other members, exports, scalar code, startup entry and
all30 Apple executable regions are checked. The ADT delta is exactly one child.

From the source pipeline, add `--bt-registry` after `--bluetool-lifecycle` and its
prerequisites. `build_bt_registry.py` directly consumes a clean-build output and
its lifecycle output; no private historical build is required. The full baseline
and appended stages have run separately; the combined empty-output invocation
is not rerun. Cache/helper/trust/menu and floor1738713600/footer0/parent3 stay fixed.

Image9138b45d1b63e4c57b041f63e9538f6376d81a5bda6b1e2066e36c92c18f430b,
session7a3381cb4c5d2ad7. Hardware confirms `device-tree=1 platform-service=1
encoding=1 speed=8000000`. Bootstrap reads still return Ready/0, then USB stalls;
no H4 connection is observed. Automatic physical fastboot/full stock restore and
Android/root/green succeed, with no confirmed synchronous RPC return. The reset
cause remains unknown. See hardware-result.json; this is not Bluetooth acceptance.

Static original17 analysis additionally explains the marconi warning: caller
0x100099c10 first looks up marconi-bt, then0x100099c20 falls back to bluetooth.
The latter prints the actual address on success. That success was already visible
before this change, so do not treat the warning as the cause of the stall or add
a fake marconi alias. Transport getters use IODeviceTree CFData properties; see
native17-lookups.json for the exact anchors and input hash.

Next inspect the owned BlueTool's actual script, reply result and send completion.
Kernel bootstrap success alone does not prove these. The existing wait sampler
first runs after120s, later than this log stop, so enabling it unchanged is not a
useful next test. Keep all controls and stop/recovery evidence intact.

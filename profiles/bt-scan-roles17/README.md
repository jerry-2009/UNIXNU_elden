# v136 correct standard/vendor scanning roles

Same-image hardware confirmation: native completion0/accepted1; byte37ff,
cache1/vendor0/standard1 and the corrected setter word are observed. Two live
rows show client1/ready1 (out59/up82, then out110/up916); at requested shutdown
the driver had out119/up1071. No legacy0x200b/0x200c refusal was recorded. The
first observed daemon exit follows our RPC ACK and driver withdrawal, SIGKILL9;
the earlier unsolicited initialization exit is not recorded in this window.
The optional0x2007/status0xc remains. Nearby discovery records, pairing and
sleep are not yet verified. See hardware.json for drop/coverage limitations.

The first attempt never exercised scanning: the PC's COM path disappeared
during open, and bluetoothd exited on an all-zero address before WCN/registry
publication. A replacement listener recovered the buffered log and typed return.
The PC logger now waits up to10 seconds across this precise missing-path case,
revalidates device/location and never retries access-denied/busy errors. Ten
host cases pass. The successful same-image repeat connected on its first attempt,
so the real transient retry branch is still supported by host tests only.
Target-side startup ordering when USB is late/absent remains an explicit gap.

v135 proved byte37=ff and that both patched instructions were present, but the
controller still received legacy0x200b. The iOS17 lower flags had been assigned
the opposite roles by our earlier adapter. Correct mapping follows actual
command submission, not diagnostic variable names or iOS27 field order:

| iOS17 field | Setter | Actual role |
| --- | --- | --- |
|0x10093c32e|0x100216ee0|Standard extended scan;0x2041 parameters and0x2042 enable|
|0x10093c32d|0x100216f34|Vendor scanner callbacks through0x100931a48/0x100931a40|

The dynamic real-command check and upper cache remain unchanged; the publisher
now writes the standard flag and disables the vendor flag. The completion
observer uses corrected labels and reads the correct setter instruction.
No capability bit or command result is forced. Native packet construction,
completion callbacks, errors, firmware, launch constraints and recovery stay.

60 cases execute the original parameter, refresh and enable senders through
the real submit boundary at two slides. They reproduce v135's legacy/vendor
paths, then check0x2041/0x2042 selection, legacy fallback for absent support,
1M scan parameters and native callback pointers with the corrected roles.
This replaces the inadequate earlier assumption that reaching the first
branch proved the final command choice. Marker bounds/copy-failure tests pass.

The candidate retains40 exact-original page rules and the40-entry bounded
parser. Source build, scalar core/native objects, other archive members,
30 original Apple execution regions, entry and AVB are independently checked.
Hardware outcomes are recorded separately; command routing is not pairing.

Use `--bt-scan-roles17` with the process-lifetime chain in build_clean, without
other native17 extension options. Individual source stages were executed;
the latest combined empty-output command was not repeated. No old v99 artifacts
or workbench source paths are build inputs. GPU remains last; audio is not enabled.

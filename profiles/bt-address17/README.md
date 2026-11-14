# v138 wait for the real Bluetooth address

Hardware confirmation deliberately connected the PC listener90 seconds after
boot. The address wait slept57 times (28.5 seconds), then the original reader
accepted the real property; native initialization returned0 and the H4 client
remained connected. Seven extended parameter commands and13 extended enable
commands received replies with final status0.349 complete extended advertising
reports reached the native socket; incomplete0/malformed0. These are reports,
not349 distinct devices or proof of native UI/cache entries or pairing.
Observed daemon exit follows the requested RPC shutdown. Full stock restoration
and Android/root/green/boot completion passed; sleep requested. Full details and
USB log losses are in hardware.json.

This validates the delayed-listener scenario, not every unplugged/charger/sleep
configuration. The separate v137 stage1/-19 power refusal remains unexplained;
v138 passed the same checks and did not exercise its stored-admission error log.

The original21H461 reader at0x10009abc0 already uses IOServiceNameMatching,
IOServiceGetMatchingService and IORegistryEntrySearchCFProperty for
`local-mac-address` in the IODeviceTree plane. The earlier daemon could run before
WCN published this property and exit on its initial zeros.

Only the call at0x100099c20 is wrapped. The wrapper waits for a CFData value of
at least six bytes with nonzero address data, then releases the object and port
and calls the original reader once. Original final address validation remains.
The wait uses at most240 half-second sleeps; allocation failure, absent service,
wrong type, short data and zero data all remain bounded. Every matching dictionary
is consumed by GetMatchingService, and every acquired property/port is released.
It never manufactures an address, changes entitlements, starts another controller,
or uses the unverified sysctl wait from v137.

16 actual instruction cases at two slides exercise immediate/delayed data,
failures, timeout, reference ownership and the original lookup return. The tests
also cover64-bit CF pointers with zero low bits and unspecified upper bits of a
32-bit Mach port return. IOKit itself is modeled; hardware evidence is separate.

Discovery accounting from v137 remains. WCN refusal logs print only already-read
admission snapshots; unread slots may be zero. No new register read, power write,
retry or relaxed voltage/identity check is introduced by that diagnostic.

Three native units and two core units rebuild from the clean source parent.
The fixed parser capacity is64 for59 exact-original, same-page rules of at most
16 bytes. Actual parser boundary tests pass. Other archive inputs, original
Apple30 execution ranges, entry contract and rollback floor remain checked.

Clean entry uses the full process-lifetime chain with `--bt-address17`, without
other native17 extension options. It regenerates rules from declared original OS
input and does not consume an old v99 build. Each source stage was executed;
the newest combined empty-output command was not repeated. Discovery records,
pairing, persistent keys, power toggles and sleep need their own acceptance.

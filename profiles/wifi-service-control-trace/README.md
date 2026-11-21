# v176 control initialization trace

v175 proves that the signed helper starts and opens the control socket, but it
repeatedly disconnects. This profile keeps the same helper, cache, private MAC,
core object, Linux runtime, hardware inputs and physical shutdown fence. One
native object adds bounded diagnostic observations.

`ELDEN_WIFI_CTL` reports:

- `getopt`: the existing session getter's actual return code and output length.
- `read`: the original mbuf reader's result and fixed header metadata.
- `receive`: the original control queue's mapped errno.
- `send-enter` / `send-return`: metadata and actual `ctl_enqueuedata` result.
- `stats`: the upstream locked counter snapshot when a client disconnects.

At most96 callback records and16 snapshots are emitted per boot. Header metadata
is magic/version/reserved/length-qualified but does not certify all attributes;
the original decoder and return code remain authoritative. No SSID, address,
key, attribute data, EAPOL or packet payload is logged. Snapshot fields retain
the exact128-byte Ath12kWifi5f7f5a8 ABI. They identify accepted/dispatched/replied
requests and last operation/status; they are not a stack trace.

Use the [v175 recipe](../wifi-service-owner/README.md), adding `--control-trace`
to `build_wifi_service_native.py`. The same core is reused. The full linker
selects this separate profile, which has its own native/asset contract. Run
`test_wifi_control_native.py --service-control-trace` with the frozen runtime
and component repository. Seven native socket scenarios plus the original
production queue/thread tests, actual stats layout, log cap and payload exclusion
pass ASan/UBSan. Host XNU socket functions are modeled. Native compilation
retains one existing warning;30 Apple execution regions and the7124-byte entry
contract remain checked. This is a diagnostic candidate, not a networking claim.

Hardware: the first INFO returned NOT_READY3; the next session received INFO0
(116B), six SET_KEY/NOT_FOUND replies8, SET_OPERSTATE0 and SET_PORT0. Two
connections/one disconnect; the second remained until the controlled return.
The only observed SCAN_REQUEST event267 went to the first failed session. No
SCAN command2 followed on the initialized session; BSS0. The native one-shot
diagnostic marks its request sent on queue success, while upstream mainline
clears the pending UI event on delivery. Next gate that test request on a
successful INFO reply for the current session. No claim that logging fixed
v175's earlier recurring failure or that radio scanning has failed.

Physical shutdown and complete stock restoration pass; capture256107B/dropmax0,
no reconnect/discontinuity, no counter after disconnect. All jobs terminal.
[Evidence](../../docs/evidence/wifi-service-trace-v176-20261116.json).

# v135 native capability observation

This diagnostic publishes the dynamic scan flags before reporting native
initialization, then supplies the relocated capability-page address to a
name/CDHash-guarded kernel marker. Five bounded copyin reads report the support
bytes, upper cache, two lower flags and two instructions, plus the existing
fixup parsed/applied counters. Copy failures remain visible and do not fabricate
HCI results. The 64-byte sampled region includes the original50-byte native
command cache; only byte18/byte37 and its aggregate nonzero count are printed.

Hardware: all five reads returned0, byte18=83, byte37=ff, cache1, field32d1,
field32e0, getter17f4b40c, setter17f7af74, parsed40/applied36. This proves the
capabilities were present and the mapped instructions executed; it disproves
the missing-capability/failed-page-patch hypotheses at this boundary.

**Historical labels were wrong:** this diagnostic called field32d `hci` and
field32e `vendor`. Exact native senders show the opposite roles. Field32e picks
standard0x2041/0x2042, while field32d enables dispatch through the vendor table.
The isolated v133 getter test missed these send paths. See the corrected
[bt-scan-roles17](../bt-scan-roles17/README.md); do not copy the old role labels.

60 actual instruction cases check observation after publication and preserve
native success/failure state. Actual marker ASan/UBSan checks cover identity,
address shape, bounded reads, copy faults and log quotas. Neither establishes
scanning or pairing. This profile still produced0x200b/status0xc and exited.

Clean entry: use `--bt-scan-observe17` with the process-lifetime chain, without
other native17 extension options. It reads declared original OS input and
rebuilds the necessary units; it does not consume a historical v99 runtime.

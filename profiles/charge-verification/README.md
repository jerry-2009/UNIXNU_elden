# v139 charging verification

Hardware normal-path check passed: bypass was verified at cycle17 with enabled0,
then stock at cycle24 with enabled1 and original/EU windows95100. Applied generations
advanced0→1→2; the listener reports sequence complete, restore confirmed and no
charge errors. After typed reset/full stock restoration, Android settings matched
the pre-trial values exactly: charging_enable1, protection_setting095100,
protection_setting_eu095100. Android/root/green/boot completion and sleep request
passed. Fault-path behavior remains host-test evidence; this is not net-charge or
dual-port acceptance. Raw log losses and identities are in hardware.json.

The old caller fed every complete poll into charge-policy verification, including
cycles that were already stale. After a SET ACK, the policy's timeout ignored
WaitWindow/WaitEnable, so missing readback could remain pending indefinitely.
The public available flag also survived loss of qualified telemetry.

This variant admits verification only from a complete, non-quarantined snapshot
younger than10 seconds in the same policy epoch. A worker-managed30-second budget
or telemetry quarantine fails an unresolved verification, without retrying SET
or claiming restoration. Availability follows the existing change-admission
conditions. Previously verified mode/generation remains historical, not a fresh
success claim when the controller becomes unavailable.

The policy's window values, 28/29 writes, wire formats, current budget, existing
health/temperature gates and firmware protection are unchanged. Actual old/new
policy and caller tests reproduce the gaps; fixed ASan/UBSan and the original146
mode checks pass. The local poll/policy epoch is used, not the separately numbered
transport epoch. The actual client baseline is the frozen6c7fbcb source in
profiles/v91/sources/power; retired direct-DC code is not reintroduced.

Two PMIC archive members rebuild, other members and core objects remain unchanged,
and scalar code, exports, original Apple30 regions, entry and AVB are checked.
Compilation uses the recorded staged working directory so relative forced
includes resolve within the clean build. The initial missing-meta_features
attempt is retained, not worked around by reading an old external tree.

Add `--charge-verification` to the full `--bt-address17` clean-build command.
The current qualified parent is the Bluetooth/address baseline. New source
stages have run individually; the combined newest empty-output command has not
been repeated. Firmware/OS/signing inputs remain declared separately.

The live check uses only bypass then stock, with verified applied generations
and Android before/after protection settings. It does not prove net charging,
dual-port source selection or full 80%/40–60% cycles. Fault injection is host
evidence; it does not claim those faults were reproduced on the tablet.

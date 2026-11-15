# v137 discovery accounting and bootstrap wait (superseded)

This experiment added a bounded wait for the existing bootstrap sysctl before
the original address lookup.22 instruction cases passed, but the delayed-host
trial exhausted1200 sleeps without a valid response; the precise sysctl error
was not captured. Independently, WCN power preparation refused at stage1/-19,
before firmware startup. Neither waiting nor discovery passed that hardware
trial. Original gates, failed artifacts and recovery evidence are retained.

The replacement [bt-address17](../bt-address17/README.md) waits through the same
IOKit interfaces already used by the original address reader. No sandbox or
identity checks are disabled.

`Discovery.inc` counts completed real UART command writes and successful native
socket deliveries. Command groups are Inquiry, legacy parameters, legacy enable,
extended parameters and extended enable. Statusffffffff means no reply recorded.
LE reports are length-validated; incomplete extended data is counted separately.
Counters saturate, retain no addresses/payloads, and are read under the bridge
lock. They establish socket delivery, not native discovery-cache or UI acceptance.
Actual parser ASan/UBSan cases cover packet truncation, multiple reports, data
lengths, credit notifications, failure status and snapshots. Original32/new56
table-capacity checks pass; this candidate has55 exact-original rules.

`--bt-discovery17` is a historical clean-source reproduction option. Individual
stages were executed; the new combined empty-output command was not repeated.

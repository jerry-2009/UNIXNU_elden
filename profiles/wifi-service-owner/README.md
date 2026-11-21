# v175 exact supplicant launch rule

v174 installed the real signed helper/cache but AMFI refused the helper with
`c[8]p[1]m[1]e[6]`. This version adapts the existing verified BlueTool RAM-overlay
rule to `/usr/libexec/unixnu-wpa_supplicant`, CDHash
`b02572b5f0fd9e79790645ad33df708b24530295`.

Admission requires prepared assets, explicit `ewt=1`, EPERM with the exact
codesigning launch-constraint reason and category string, launch type1,
CS_VALID+CS_SIGNED, no MAC-policy error, regular file and read-only union bindfs.
Other launch errors and executable-page verification are unchanged. Process
name truncation is deliberately not used as identity; the exact vnode path and
CDHash are both required. No global AMFI or signature check is disabled.

Use [v174's build steps](../wifi-service/README.md), adding `--owner-launch` to
`build_wifi_service_core.py`. The core recipe replays the current closed SDK
overlay and pins the original common source before inserting the predicate.
The existing v174 native worker and all service/cache/trust/private MAC inputs
are unchanged. The full linker selects `wifi-service-owner`; its own source,
owner, native and asset contracts are audited by the usual entry/boot tools.
Run `test_wifi_owner_launch.py`; its actual predicate tests preserve all prior
failure fixtures except the deliberately unused process name. ASan/UBSan and
11 asset-rejection tests pass; core91/native1 warnings remain.

Hardware now admits the helper and records31 real control connections and30
disconnects. These are repeated initialization attempts, **not a stable service
or networking success**. BSS remains0. The original AMFI message appears before
the explicit accepted marker and does not mean the scoped admission failed.
Next observe actual getsockopt/INFO/receive/send results without recording keys
or frame payloads; inspect the unchanged upstream client before changing logic.
The native BSD/IOKit network bridge is still pending.

The full physical fence and automatic stock restoration pass. Last Android is
root/green with original charging/radio/scan preferences restored and sleep
requested. Capture has40 reported dropped bytes; do not call it lossless or
infer a precise missing transaction from this log alone.
[Evidence](../../docs/evidence/wifi-service-owner-v175-20261116.json).

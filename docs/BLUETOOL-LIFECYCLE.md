# BlueTool lifecycle integration

Update: v127 now embeds and mounts this cache/signature before launchd. Two real
trials pass cache stage5/status0 and full readback; the later log stall remains.
Receive-only capture of the same image also stalls, so periodic PC queries are
not necessary for it. See profiles/bluetool-lifecycle. The preparation-only
description below records the preceding component step, not the latest state.

The original21H461 job and its cached copy are identical, hashes
e6a3c88d… and f1b99c4e…. The current runtime had retained that job deliberately.
Sheng's successful native integration applies four overrides through official
`build-boot-runtime.py`. The exact reviewed references are QcaBluetooth
22ff97f93416452335bb61badb14c762da653487, UniXNU14236be44fd56fb94d11594864ffb70780352150,
and Sheng1108068537d5396edb2c63b2f8c6f5b97b0a4bbc.

| Field | Original21H461 | Owned helper configuration |
| --- | --- | --- |
| UserName | mobile | root |
| EnableTransactions | absent | true |
| EnablePressuredExit | true | false |
| ThrottleInterval | 0 | 3 |

POSIXSpawnType stays Adaptive. Label, executable arguments and the
com.apple.BlueTool Mach service stay unchanged, as do the other560 jobs and all
other cache top-level values. These are lifecycle conditions for our XPC helper;
the difference alone does not establish the cause of USB loss in v124–v126.

`tools/build_bluetool_job_cache.py --os-image ORIGINAL_OS --trust-cache
CLEAN_BUILD/generated/runtime/runtime.trustcache --output NEW` builds the candidate
from declared original inputs. The OS image is mounted read-only and detached.
Original cache/job hashes must match. Apple plutil serializes the merged plist;
the host private XPC parser validates the four fields and561 jobs. A detached
SHA256 signature is generated and verified, and one exact cache CDHash is
appended to the existing trust container, preserving every old module.

Prepared outputs (not installed):

- cache925323B, SHAd258da13c01861a229fe64153e239750d5e9253ff53b692c2db76e782bbfc98d;
- CDHash3dd1063e4d38d18da8f4c753b5ca25a6efe1e92a;
- trust SHAdaf63a9153addabce3c9f8b3ee532af6ecb062ceca469271bb634b9ad52f105c;
- headerSHA5a1e7b118150736f053b64d9e157f1d41ce961249a3e65201febfbcbbba51986.

Mac output is the current project's isolated/bluetool-job-cache; Windows workbench
edl_work/bluetool-job-cache-20261114 and lab/records/bluetool-job-20261114 hold the
files and report. No new boot contains this cache yet. The target17 parser,
runtime mount, native trust consumption and functional Bluetooth remain untested.

Next integrate cache/signature into the qualified RAM runtime before launchd,
with a narrowly bounded writer: the existing IconServices helper only accepts
131072B, less than this cache. Do not silently loosen that general helper or
replace original root files. Verify the read-only union and exact cache length,
retain all old trust modules, rebuild from source and independently audit the
complete image. The clean-build option must generate these new inputs itself.

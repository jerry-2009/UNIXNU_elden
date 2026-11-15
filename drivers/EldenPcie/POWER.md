# PCIe power provider — explicit diagnostic budget

The native WLAN owner now has `elden_wlan_root_power`: a real cmd-db/ARC/VRM/BCM
plan sent through the existing qualified RPMh implementation, with physical LDO
readback. Source/native compilation and component linking pass. **New votes have
not run on Y700**; this round's device operation was a bounded stock read only.
Root mappings/pins/shared-GCC glue and a whole kernel are still pending.

## Board evidence

Fixed TB322FC Linux6f97250e assigns PCIe/PHY supplies to `ldof1`880–920mV and
`ldog3`1200–1256mV. The stock SPMI regmap observation reads PPIDs5c1/6c3:

| Supply | Type/subtype | Voltage | Mode | Status/enable |
| --- | --- | --- | --- | --- |
| L1F | 04/ad | 880mV | 07 HPM | 87/80 |
| L3G | 04/ad | 1200mV | 07 HPM | 87/80 |

Both read cursors returned to their original address/count and the private
debugfs mount was removed. Its empty temporary mount directory was retained.
No PMIC data register, charge setting, boot image or GPU worktree was changed.

The actual SM8750 interconnect has `SN4` on `qns_pcie_mem_noc`, buswidth8,
one channel; `SH1` is a boolean enable-mask BIT0 resource. It is not Sheng's
SN7/buswidth16 or the GPU's SH0 bandwidth resource. The diagnostic minimum
calculation follows Linux `bcm_div` truncation with minimum1 for a nonzero
sub-unit value, and vote_scale1000. It does not import another board's ceil rule.

## Budget policy and limits

APPS DRV2 boot-time ARC/BCM votes cannot be read back by the current provider.
Writing a nominal/minimum value could lower an unknown retained request from
another consumer. The first provider therefore requires the explicit boot
argument `elden-pcie-full-on=1` and an explicit diagnostic policy:

- MX/CX use their actual firmware cmd-db table maxima, with MX first. Tables
  must be strictly ordered and cover the requested generation's minimum64/256.
- SN4 uses saturated14-bit x/y votes. The smaller calculated PCIe requirement
  is reported separately; it is not described as the applied value.
- SH1 uses its actual boolean enable. No MC0, ACV, gfx or SH0 request is sent.
  This is a root/configuration bring-up budget, not validated DDR/DMA throughput.
- LDO targets retain the larger of the measured, required and previously held
  values, within the exact board ranges; HPM/enable are explicit. No disabled
  or lower vote is sent during stop. Successful votes remain until platform reset.

**This is not a default or a daily power-saving policy.** It may increase power
use. Shared vote ownership, efficient steady-state budgets, suspend and qualified
down-voting remain work before promotion to normal operation. A future diagnostic
must retain temperature/deadline/stock-restoration checks; this source-only result
does not grant a hardware acceptance claim.

## Native admission and failure behavior

The entry requires the matching provisional WLAN provider/epoch, explicit boot
intent, thread context, ready recovery RPC, at least60 seconds of recovery budget,
the existing fresh charge-policy gate and a valid5–38°C battery sample. That
charge gate includes the established voltage/health/input checks. Transport
epoch is pinned and rechecked before and after sending.

All cmd-db identities, physical type/subtype/ranges, resource distinctness and
the complete10-command plan are validated before the first new vote. The same
platform/WLAN gates serialize with Bluetooth and other supply operations. The
existing SPMI transaction gate and `Sm8750RpmhWriteActive` provide actual physical
I/O; no private successful stub or second sender is introduced.

TCS failures after programming, failed LDO readback, or freshness lost after a
successful send become Held. No new plan is published and no speculative
rollback is attempted. A repeated successful same-epoch request sends nothing;
SPMI/RSC uncertainty still refuses it. Root-clock/DMA readiness is not inferred
from this acknowledgement alone.

## Validation and reproduction

85 native component scenarios/1386 checks pass ASan/UBSan, including the prior
native/GPIO cases, explicit-intent/freshness refusals, all28 before/after physical
LDO read failures, pre/post-program TCS errors, bad readback, changed transport
epoch, corrupt/missing resources, monotonic ARC/range checks and retained floors.
The cmd-db/ARC/BCM helpers are the actual frozen code; physical SPMI/RSC callbacks
are modeled. An initial test-only enum conditional failed `-Werror`; the cast was
corrected and all attempts retained. No hardware votes were executed.

ARM64/iOS17 plan object:
`068b0463b2629a49736b4719ef4087af28dca291484ef7292ba35f2b2dae9131`.
Native provider:
`0aef24b565af802c80c51b9128cd054909d0c4d1eb2b0c5a983408c256ef7890`.
Plan/native/WCN/existing RPMh relocatable binding:
`d3f5491e23cb9764ae10b4747be6fb6ab337c3e027fb5cddde95f5d99794d2de`.
Remaining imports are present in the verified v156 kernel. The plan is warning-free;
the native object retains its one existing manufacturer conversion warning. No
FP/SIMD or initializer is added; this is not a whole kernel link.

```powershell
py -3.12 tools/test_pcie_power.py --wsl-distro Ubuntu --output C:/Users/Public/pcie-power-test
py -3.12 tools/audit_pcie_power_sources.py --linux-repository /path/to/tb322fc-linux-kernel --stock-record /path/to/stock-record --output /new/power-audit
```

```sh
python3 tools/build_wlan_power_native.py --root-power --clean-build /source-built/unified --llvm /path/to/llvm/bin --output /new/native
python3 tools/build_pcie_power.py --clean-build /source-built/unified --native-build /new/native --wcn-build /source-built/wcn-core --llvm /path/to/llvm/bin --output /new/power
```

The second command binds the exact existing8d4d7196 RPMh object from the clean
baseline, not a duplicate sender. Evidence: [power record](../../docs/evidence/pcie-power-20261116.json).
Mac `lab/pcie-power-20261116/{native1,power2}`; workbench matching `edl_work`
and `lab/records/pcie-power-20261116/{stock,host6,source-audit1}`.
Next connect native mapping/pins/GCC ownership and worker/quiesce handling to
Root.c, then full-kernel recovery qualification before a bounded hardware run.

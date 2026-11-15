# Elden PCIe cold bring-up components

Follow-up: the [root transaction](ROOT.md) now compiles and binds this PHY,
covering clocks/GDSC/PARF/SID/L0/config with1840 host scenarios. Real native
power/NoC/mapping callbacks, the full kernel and hardware are still unfinished.

This directory currently contains the exact TB322FC PHY table and a bounded
cold PHY transaction. It does **not** yet contain a complete root-complex,
DMA/MSI or MHI driver. The PHY and revised WLAN/QMI objects compile offline;
no new kernel/image was built or tested on Y700 in this round.

## Board evidence and table provenance

Stock Android identified HA2A1PT2/TB322FC, boot complete/green,100%/4451mV/Full,
zero reported battery current, charging enabled and both windows095100. Settings
were read only. This full-battery observation is not a protection-cycle test.

PCI sysfs caches identify root17cb:011c and endpoint17cb:110e, BAR0 at40400000
for2MiB and BAR2 at40300000 for32KiB, with32 MSI IRQ entries. The endpoint was
runtime-suspended: its256-byte configuration read returned allFF, link-speed
queries failed and width255 is invalid. These cached assignments are **not a
fresh, powered endpoint identity or link-training result**. The initial capture
script stopped on that allFF result; the bytes and log are preserved rather
than interpreted as valid PCI configuration.

`board-facts.json` contains only selected hardware facts from the actual running
FDT, SHA256 `b060f1001c4907895656c967fe3b2e5f6fb4d350be65cd79e4e3f4cdff1a8a45`.
The full FDT remains in the private workbench; a clean clone can regenerate the
table from the published facts without that full snapshot. Registers are at
PCIe0/PARF1c00000, PHY1c06000, DBI40000000, iATU40001000 and config40100000.
The CESTA window is recorded as a fact and is not accessed by this component.

`prepare_pcie_phy.py` checks the exact ArmadaOS TB322FC Linux lineage,
`6f97250ead155fc3b980856323e99a4623dae73d`, its SM8750 gen3x2 configuration,
v7 block offsets and four register headers. It preserves the127 stock writes
in order. Compared with that Linux table:

- RX offsets1380/1394/1b80/1b94 use8f in stock versus9c in Linux.
- Stock writes5e4=0f; Linux names EQ_CONFIG2 at5e0 instead.
- Stock also writes1800=0. These differences are recorded, not silently merged.
- The referenced Pagani table has an additional8f8=1f write absent from Y700;
  it is not imported. Pagani rails, DMA reservation and PHY table are not Elden
  board evidence.

The comparison identifies differences; it does not prove which tuning is best.
This initial Elden transaction uses its OEM table. `PhySequence.inc` SHA256 is
`15a669913b5aef092eb1cf556561caac7a6cb9fdc5c52cecf2e1ac04f11fcc24`.

## Transaction and prerequisites

Ordering follows the working Sheng `WifiProbe.cpp` bringUp method and Linux
`qmp_pcie_power_on`: program the table, switch PIPE to the PHY, release PCS
reset, start and poll PHYSTATUS. The values and v7 offsets are Y700/SM8750,
not Sheng's SM8550/v5 PHY layout.

The caller must own cold bring-up, keep PERST# low, verify the current WLAN
power lease, rails, GDSCs and required clocks, and serialize with shutdown.
Every MMIO operation requires its real admission callback. This callback is
not yet implemented in a native root-complex driver; it must not be replaced
with constant success. An unclocked MMIO access may stall before software can
time it out, so these prerequisites and the existing hardware watchdog remain
necessary.

The transaction checks initial PCS reset/start, emits125 preparatory writes,
requires real pipe-source acknowledgement, then emits reset-release/start.
It verifies control readback and PHYSTATUS within10ms and a finite poll budget.
AllFF, I/O errors, stop admission, late success, stalled/backward counters and
readback failure refuse readiness. An attempted write leaves terminal Held on
error; no implicit retry, guessed rollback, rail disable or other pin change.
Ready means PHY status only, not L0, endpoint presence, DMA or networking.

## Cold WLAN identity ordering correction

The previous provisional native API documentation required live endpoint
identity before power acquisition, which cannot work for a powered-down chip.
The revised `WlanPower.h` makes the distinction explicit:

1. Match the real TB322FC/SM8750 board/root resources. `expected_vendor` and
   `expected_device` come from that board description. Acquire the provisional
   power lease; `power_check` permits power/link preparation only.
2. Establish the root link, read actual config17cb:110e and the Peach major2
   identity through BAR access, then call `power_confirm_endpoint` for the same
   provider/epoch. Never use cached sysfs values as those fresh reads.
3. `power_ready`, native CPR and QMI binding require this confirmed epoch.
   Stop/reacquire clears confirmation; wrong identity, unknown/allFF and stale
   epochs cannot authorize QMI. Quiesce/stop remain possible before confirmation.

The PCIe/MHI caller still needs implementation. No placeholder proves that the
root or endpoint is ready, and no current boot candidate uses this interface.

## Validation and reproduction

281 actual PHY transaction scenarios/83426 checks pass ASan/UBSan, including
every fallible admission/MMIO/pipe callback, reset/readback refusal and timing
failures. Hardware callbacks are host recorders. The ARM64/iOS17 PHY object
`b35bfcc847768af23b43c669b284bacd98dc01b6a79fb444125f1178333fb2d0` has one export,
no imports, no FP/SIMD or initializer, and zero warnings.

The revised cold-owner/QMI chain passes47 combined host scenarios/450 checks,
including refusal before confirmation and rejection of allFF/wrong/stale IDs.
Native owner `32cfdd70b48f83f1a2b14082e48f154cc2338b5b31a035af70a8bab13d133431`
and QMI gateway `5ea37619e9088233c506fd1373d8c36b0a508dc4a7a46cdd1b823dea2b09251b`
compile. The128-object relocatable link again resolves the real gateway;
the prior1 native/14 inherited shim warnings remain. No complete kernel link
or hardware acceptance is implied.

```powershell
py -3.12 tools/prepare_pcie_phy.py --linux-repository /path/to/tb322fc-linux-kernel --output /new/phy-table
py -3.12 tools/test_pcie_phy.py --wsl-distro Ubuntu --output C:/Users/Public/phy-test
py -3.12 tools/test_qmi_power.py --wsl-distro Ubuntu --output C:/Users/Public/cold-owner-test
```

On macOS, `build_pcie_phy.py --llvm /path/to/llvm/bin --output /new/native`
compiles the PHY. Rebuild the owner with `build_wlan_power_native.py`, then use
its new output with `build_qmi_power.py`; do not combine the new gateway with
the older owner lacking `power_ready`. See the linked component READMEs for
their source-built input arguments.

Evidence: [board/PHY/cold-owner record](../../docs/evidence/pcie-cold-20261116.json).
Workbench: `lab/records/pcie-source-20261115`; Mac:
`lab/pcie-phy-20261115/native1` and `lab/pcie-cold-owner-20261116/{native1,qmi1}`.
Next implement root clocks/GDSC/PARF/PERST/LTSSM and real config/DMA/MSI/MHI
callbacks before full-kernel recovery qualification and one hardware trial.

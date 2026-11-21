# v158 PCIe BAR and Peach identity trial

The complete signed candidate passed one TB322FC hardware trial. PCIe remains
Gen3 ×2; actual config discovers BAR0=2MiB and BAR2=32KiB, assigned at0x40400000
and0x40600000. CPU reads through the Peach window return chip0x40210200,
major2/minor0. The native WLAN provider accepts the actual identity and epoch.
Endpoint command is0x0002: memory decoding enabled, I/O/bus mastering disabled.

This is not Wi-Fi availability. SMMU/DMA/MSI, MHI, firmware, network callbacks,
scanning/association/traffic, and daily power acceptance remain pending.

## Source and build

`EndpointNativeSource.py` derives the optional worker from the unchanged v157
root sources. New native map/read/write callbacks use the existing inhibited
cache IOKit mapping and scalar MMIO. They require the current root/power epoch,
the discovered BAR0 address/extent inside the stock aperture, and permit just
the Peach remap-control write. Kernel stop waits for this worker as well as
the root; mappings stay until reset and the terminal identity status withdraws
confirmation as soon as stopping begins. The original root status ABI remains.

`epe=1` opts into the endpoint stage after all three existing root/WLAN/full-on
intents. The signed menu uses1015 bytes, preserves8-second countdown, fallbacks,
thermal/charging/watchdog/SSV and sync recovery. Bluetooth bring-up remains off.

The native builder uses its existing explicit source-built SDK/root/power/WCN
arguments plus `--endpoint-build <build_pcie_endpoint-output>`. Pass that same
option and object directory to `build_pcie_root_kernel.py`. The latter produces
profile `pcie-endpoint-trial`; packaging uses the usual `--wcn-report` and
`--bt-runtime` arguments documented in [v157](../pcie-root-trial/README.md).
`audit_pcie_kernel_hooks.py --endpoint` additionally proves the actual identify
and native-confirmation branches and their unchanged prelink bytes.

The full build replaces3 existing native objects and adds5 PCIe objects; core
objects/filelist, other archive members, UFS initializer targets, all30 original
Apple executable ranges and the7124-byte entry/return relation are retained.
UFS keeps its normal32-slot/IRQ/AH8 behavior without another diagnostic read loop.
No full new empty-directory `build_clean.py` invocation is claimed; the entire
source-built parent and explicit component stages were used.

Native worker SHA256:
`62cbbdf5bc1aab1778c1d2f987035b6e42eb110fec0f2358262b1e4d24a3a1bf`.
Raw kernel SHA256:
`1278eb40263041c1dde4167c937ae9e22c4b7e9c67c32350596eedf3493a13e1`.
Signed boot SHA256:
`1990cca48d1300e16d95c1ad87012e9b371274b61f2d083762db9afd4e208d22`.
Session: `a6f4850f8a2715a7`. Floor1738713600/footer0/parent3 remain unchanged.

## Verification and limits

The actual derived worker/root/endpoint/PHY path passes30 host scenarios/5519
checks, including the20 prior root scenarios, map failure, wrong chip, remap
failure, stop during read/confirmation, and native-confirm/ready errors. Physical
kernel/power/MMIO services are modeled in this test. ARM64 worker compilation
has no FP/SIMD/initializer or warning; native binding resolves the real identity
and power providers. One initial host compile rejected misleading indentation
in a test callback; fixed source and original failed log are retained.

Hardware reports:

```text
ELDEN_PCIE_EP end rc=0 state=2 stage=8 chip=40210200 major=2 minor=0 command=0002 mapped=1 remap-restored=1 confirmed=1 writes=28 last=6:0000001c=00000000
ELDEN_PCIE_EP bars bar0=40400000/200000 bar2=40600000/8000 epoch=1 dma=0
```

Root power requests and LDO reads match v157; the explicit full-on budget is
still diagnostic. The log contains164526 bytes and reports21 dropped bytes,
with no reconnect/discontinuity. Required root/endpoint/recovery lines are
present; the whole log is not complete. The final status precedes disconnection.
The early commanded return interrupts the existing PD bootstrap with restored1;
it is not a fresh full PD-cycle acceptance. Storage-not-ready messages occur
only after RESET_AFTER_SYNC.

The host observed physical fastboot after sync/PERST-low quiescence, verified
the entire stock boot SHA, and restored Android/root/green/boot completion,
original charging/radios/background scans. Sleep was requested. The trial and
all associated jobs are terminal; any next write requires fresh admission.

The capture assessor accepts `--endpoint`;21 rehashed negative cases reject
wrong IDs, missing stages, bus-master enable, wrong chip/BAR/confirmation,
missing recovery and incorrect stock/settings restoration.

[Machine-readable evidence](../../docs/evidence/pcie-endpoint-hardware-20261116.json).
Workbench: `edl_work/live-pcie-endpoint-v158-20261116`;
`lab/records/pcie-endpoint-native-20261116` contains host2, hardware-final and
capture-tests1. Raw log `usb/20261115-194335.bin` SHA256:
`55d541503512ea2b4df412870516d5316185c45c1d5d626c2d45ac1c779ece83`.
Mac builds: `lab/pcie-endpoint-native-20261116/native1`,
`lab/pcie-endpoint-kernel-v158-20261116/build1`,
`lab/pcie-endpoint-boot-v158-20261116/package1`.

Next implement owned SMMU/DMA and MSI plus real draining before any bus-master
enable, then attach MHI/Peach/QMI. Do not repeat this identity-only trial.

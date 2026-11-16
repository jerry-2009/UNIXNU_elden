# v164: full Wi-Fi MHI runtime candidate

This candidate includes the real Linux runtime, native DMA/MSI/config/firmware
callbacks, actual QMI consumer binding and native bus-master admission. It is
not a mapping-only probe. Hardware validation is pending at this commit.

Six original firmware files are checked before entering the runtime. The PCI
adapter binds its real device, verifies MSI programming and only then requests
master enable from the native owner. The worker starts by polling like the
upstream board; it switches to IRQ delivery only after actual nonzero MSI bits.
Once firmware reaches the radio-ready stage it requests one scan, with at most
three bounded attempts. There is no association credential or userland network
interface claim in this profile.

On stop, new firmware/DMA admission is withdrawn while existing completion
processing remains available. After the Linux stop returns, the native path
observes or requests MHI reset, accepts only RESET or READY+READY-bit with reset
clear and no system error, disables PCI master and waits for transactions to
clear. MSI handlers stop before PERST; SMMU IRQ withdrawal follows successful
PCIe quiescence. Any failed proof retains resources until platform reset.
This protocol proof does not authorize freeing/reusing the DMA backing early.

Validation completed:

- Exact public runtime ABI layouts and all field types checked against pinned
  Ath12kWifi5f7f5a8.
- Six composed native MHI scenarios / 112 checks under ASan/UBSan, using actual
  config, MSI, reset and QMI-binding code; Linux runtime, physical services and
  DMA/firmware providers are models. No hardware result follows from these tests.
- Native runtime and WCN compile; all three new hook imports and the real QMI
  power symbol resolve with the 125-object stack. No new FP/SIMD/initializer.
- Complete kernel: five existing native replacements and 147 added component
  objects. Core inputs, other archive members, 30 original Apple executable
  ranges and the 7,124-byte entry relation are preserved. The original modem
  reader is reused instead of being linked twice.
- Seventeen direct call targets and their prelink bytes checked, including
  runtime start/stop, QMI binding and native protocol stop.
- Menu is 1,023 bytes with `ewt=1`; original countdown, fallbacks and guards
  remain. Original 56 MiB FAT / 96 MiB signed boot layout is sufficient.

Raw kernel SHA256:
`7c37ee2b67439e0d63d30668f59d009c5f1b4c472d2258d651b23a4b6799b927`.
Signed image SHA256:
`40261a3af0c1b4e847d4cd97a2d380685d0b434bcaabfc5f58aadbbc0a0a7d13`.
Session `4afa1ad04324c09f`; rollback/footer/parent remain `1738713600/0/3`.
All 173 native-source inputs match this tree.

Final Mac outputs: `lab/wifi-mhi-runtime-20261116/{source4,host3,stop1,wcn1,native2,kernel1}`
and `lab/wifi-mhi-boot-v164-20261116/package2`. Matching workbench outputs are in
`edl_work/`. Initial host fixture errors and the rejected old QMI object are
retained. Packaging1 caught a missing new-profile trust routing case; package2
uses the original qualified trust assets and passed the complete audit.

Reproduce with `build_wlan_power_native.py --root-worker --smmu-domain --mhi-runtime`,
`build_mhi_stop.py`, and the native PCIe builder's explicit runtime/stop/QMI
inputs. `build_pcie_root_kernel.py --mhi-runtime` requires the prefault-memory
variant and the reviewed source-built parent. Then run entry, boot packaging
and independent audit using the resulting runtime report. The saved native
contract qualifies this complete kernel; do not flash a raw component.

Next run one supervised hardware trial and distinguish firmware/MHI state,
actual MSI delivery, scan results, clean protocol stop and full stock restore.
The full peripheral Goal and charging validation remain incomplete.

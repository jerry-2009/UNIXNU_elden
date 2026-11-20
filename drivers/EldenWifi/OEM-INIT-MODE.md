# Preferred mode in WMI initialization

The actual first-access trial sometimes passes INFO and sends SCAN, but UMAC/CE
state subsequently becomes zero. Command-level MHI/UMAC ownership does not
recover the lost state: the first PMF handshake times out after50ms while MHI
stays M0 and references remain held. Stop/fence/put and full stock restoration
passed in the command trial. These contrasts remain diagnostics.

The original firmware advertises modes0 and5 and two physical pdev capabilities,
while the retained Linux single-pdev path omits the WMI_INIT mode table and
later requests DBS1. The OEM initialization source chooses its preferred
capability mode in WMI_INIT, except SINGLE, and derives physical band-to-MAC
parameters. Its serializer emits those original TLVs. The logical interface
alias0 is a distinct contract and remains unchanged.

Sources at `d50b305f7da9e14715a25120a4ac7b1a4b8b97c3`:

- `qca-wifi-host-cmn/target_if/init_deinit/src/init_cmd_api.c`,
  `init_deinit_send_init_cmd` and `init_deinit_derive_band_to_mac_param`.
- `qca-wifi-host-cmn/wmi/src/wmi_unified_tlv.c`, `copy_hw_mode_in_init_cmd`.
- Loaded TB322FC module33869cd6 retains the band-map helper at0x9546c/684B.
  Private module bytes are not committed.

`OemInitMode.inc` prepares the existing initialization argument only for Peach
single-pdev hardware. It uses the actual preferred mode and collected physical
pdev/PHY/regulatory capabilities, refuses invalid or duplicate entries, and
keeps all existing command serialization. `OemInitModePatch.py` omits only
Peach's subsequent mode switch; other hardware keeps the original path.
No live CE configuration or speculative clock change is made.

34 actual init-wrapper/helper cases pass ASan/UBSan with firmware calls modeled;
64 composition mutations and complete scalar/native/prelink/30Apple/entry7124/
boot-signature checks pass. PCI/WMI/core inherited warnings remain. New ARM64
objects replace only core/WMI; the state observer, original-shadow notification,
actual WCN/battery pair, epd0 and physical-return protections are retained.
This source match is not proof that the target accepted the mode or networking.

```text
python tools/test_wifi_oem_init.py --cc CLANGXX --core-source TIMELINE/core.c --wmi-source TIMELINE/wmi.c --output HOST
python tools/build_wifi_oem_init.py --runtime-build BASE --parent-build STATE_RUNTIME --timeline-build TIMELINE --llvm LLVM --output RUNTIME
```

Then use the qualified net17 composition, entry preparation and boot/audit.
[Candidate and source hashes](../../docs/evidence/wifi-oem-init-20261120.json).

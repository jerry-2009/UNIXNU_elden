# v157 root hardware result — 2026-11-16

On the TB322FC/SM8750, one bounded cold trial trained PCIe Gen3 ×2 and read
root17cb:011c and endpoint17cb:110e. All 127 board PHY writes completed; the
root controller recorded430 writes and released the GCC lock. The endpoint
command low16 was0: I/O, memory decoding and bus mastering remained disabled.

```text
ELDEN_PCIE end rc=0 state=2 stage=11 root=011c17cb ep=110e17cb link=30230008 last=6:00000004=00100000 writes=430 phy=127 gcc-held=0
```

This validates the root/PHY/config path only. There was no BAR assignment,
DMA, MSI, MHI, firmware upload, network interface or connection test. Peach
major2 still requires a real register read; the strict confirmed power/QMI gate
has not been satisfied merely by seeing PCI device110e.

The explicit full-on diagnostic requested MX level448, CX480 and saturated
SN4=16383 (calculated minimum3773). These are acknowledged requests, not measured
ARC voltages. Physical PHY LDO reads were880/1200mV, mode07/status87/enable80.
The policy is not an accepted daily power policy. It sends no MC0/ACV/gfx/SH0 vote.

Recovery completed in order: RPC ACK, UFS AH8 restored, root quiesced with
PERST low and no driver DMA, then SDAM reset-after-sync. Physical fastboot and
the full stock boot SHA were verified. Android was boot-complete/root/green;
original charge settings, both radios and background scanning settings were
restored, and sleep was requested.

The retained capture contains145944 bytes, reported drop maximum0 and no
reconnect/discontinuity. The last status precedes disconnection; it does not
prove an unavailable post-reset counter. Storage-not-ready messages occur
**after** RESET_AFTER_SYNC, not during root bring-up. The requested early return
interrupted the existing PD bootstrap at phase7/error4 with restored1; this is
not a fresh acceptance of the entire PD sequence.

An earlier preflight aborted before flashing because stock Bluetooth's shell
wait-for-state command failed. The cold retry disabled and saved both background
scanning settings, then confirmed OFF through dumpsys. The original settings
were restored after the trial. The aborted attempt and its failure are retained.

Evidence:

- [Machine-readable result](../../docs/evidence/pcie-root-hardware-20261116.json).
- Workbench run: `edl_work/live-pcie-root-v157-20261116-cold`.
- Raw log: `usb/20261115-191318.bin`, SHA256
  `27b922beb313e76e62c219b48df6c03dc1f5543af73b4b88da8993fa23b93059`.
- Candidate/audit: `edl_work/pcie-boot-v157-20261116/package1/boot`.
- Assessment and 14 rejected mutation cases: `lab/records/pcie-native-20261116`.
- Stock SHA256: `8b8e72dad85a65d3bf6fc2c6b2a88064d0487e4696ae578e9fd4c46a33565890`.

Floor1738713600/footer0/parent3 remain unchanged. No Wi-Fi readiness or complete
charging/peripheral acceptance follows from this root result.

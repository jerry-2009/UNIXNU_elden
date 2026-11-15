# PCIe0 root transaction — offline component

The [native worker and v157 kernel](NATIVE.md) now connect the mappings, pins,
power and shared GCC callbacks. The complete kernel is built, but no signed boot
or hardware result exists yet; the component history below remains scoped as written.

Follow-up: [POWER.md](POWER.md) now provides the real native supply/NoC sender
under an explicit diagnostic full-on policy. Native maps/pins/GCC/worker glue,
whole-kernel integration and hardware validation remain pending.

`Root.c` now drives the cold root sequence through the existing PHY component:
PERST assertion → real power callback → GDSC/clocks/reset → PARF → PHY →
BDF/SID → root configuration → timed PERST release → L0 → CFG0 mapping →
fresh endpoint ID. The endpoint's I/O, memory decode and bus-master bits are
then cleared/read back. No DMA, SMMU context takeover, BAR assignment, MSI
enable or MHI firmware transaction is performed.

This is a compiled/tested transaction component, **not a complete native driver
or hardware result**. Its mapping, board/power/NoC admission and pin callbacks
still need a real native implementation. Constant-success callbacks do not
satisfy those requirements.

## Source checks and important differences

The order follows the working Sheng `package/WifiProbe.cpp` bringUp approach.
Registers and clock semantics come from fixed TB322FC Linux
`6f97250ead155fc3b980856323e99a4623dae73d` and the published stock board facts.
`audit_pcie_root_sources.py` checks7 actual Linux files and binds the source SHA.

- Both SM8750 GDSCs specify `POLL_CFG_GDSCR`: completion is **bit16 of GDSCR+4**,
  at6b008/6c004. Bit31 of the main GDSCR is not the selected Linux check. The
  host fixture deliberately leaves bit31 high while withholding bit16; no
  PARF/DBI access follows that incomplete transition.
- GDSC collapse votes are bits0/2 of5214c. Linux's per-domain wait fields and
  retention flip-flop bit are preserved, without changing unrelated masks.
- Twelve branches use vote masks52008:7f and52000:581800. The check follows
  their actual `BRANCH_HALT_SKIP` and live HWCG-bit semantics; idle hardware
  gating is not mistaken for a missing enable vote.
- RCG addresses are6b084/6b068 and PIPE mux6b080. Divider-one is encoded1 as
  in Linux; Gen3 rate-change uses GPLL0-even selector6/divider3, value605.
  Other generations select19.2MHz. The mode/HW-control fields use mask10371f.
  Existing pending updates are refused; new updates may complete after branch
  votes, as required by the shared RCG path.
- The TCSR resource starts atphysical f204008, so its register0 is accessed at
  offset8 in the mapped f204000 page. It is not Sheng's TCSR address.
- BCR assertion/deassertion delays are checked against the real counter, not
  merely assumed after a void delay callback.

The root-complex model remains the SM8550-compatible ops1.9.0 selected by the
actual SM8750 DTS. This does not make SM8550 PHY data or GPIO values valid for
Elden: the127-write v7 PHY table remains the one already qualified from Y700.

## Transaction contract

`Root.h` defines the native boundary. Before any operation, admission must
verify the matched board, exclusive cold ownership, stop/recovery/fresh-power
conditions. `pins(false)` must really configure CLKREQ103 and hold PERST102
low, with readback, **before** `power_up`. The latter must obtain the provisional
WLAN lease and real PHY-supply/interconnect/corner votes. Gen3 requires the
board's NOM256 CX/MX budget, not merely a nonzero WLAN epoch.

GCC read-modify-write operations require the existing shared GCC owner. Other
vote bits are preserved. On uncertainty, the transaction records Held and
retains mappings/votes and any held GCC gate until recovery; it does not guess
a rollback or retry. All PARF/PHY/DBI/iATU/config access is gated until the
clock transaction has completed. This is still dependent on honest native
callbacks and the established watchdog: software cannot time out a CPU already
stalled inside an unclocked MMIO load.

After the PHY completes, the256-entry root-local BDF table is cleared and
read back; RID0100 gets SID offset1 at CRC8 slot15. The controller is exclusive
to this board's root/endpoint, not a generic bus enumerator. Root17cb:011c,
capability-chain bounds/cycles, target speed, L0 and sane negotiated speed/width
are checked. Gen1/2/3 are supported by the component; this is not proof that
hardware trains to the requested maximum.

The single outbound CFG0 region exposes only bus1/device0/function0's4KiB
configuration window. AllFF identity is polled within1s; real transport errors
stop immediately. Any nonmatching endpoint refuses readiness. PCI command
writes zero the upper status half to preserve W1C status bits. The endpoint is
returned with I/O/MEM/BM off pending actual BAR/DMA qualification.

`EndpointVisible` is intentionally a limited result: the cold WLAN interface
still needs a fresh Peach major2 read before QMI can be confirmed. Config reads
are bounded/aligned and refuse nonready state. Root hotplug, general PCI bus
enumeration, suspend/resume and safe DMA shutdown are not implemented here.

## Validation and reproduction

1840 actual root+PHY scenarios /3588395 checks pass ASan/UBSan: all fallible
callback positions, three requested generations, delayed endpoint response,
GDSC-bit31 false-positive guard, stuck updates/branches/PHY/link, bad endpoint,
missing power epoch, nonadvancing time and capability cycles. It also checks
preserved unrelated votes/status, the disabled endpoint and terminal failures.
Hardware and platform dependencies are modeled; no Y700 function test ran.

ARM64/iOS17 compilation is warning-free, scalar and has no initializer.
Root object: `c60809bb1740bbe2a22878cb7e4ee3e6516e4cc551654c8c382d103651656aa4`.
PHY remains `b35bfcc847768af23b43c669b284bacd98dc01b6a79fb444125f1178333fb2d0`.
The combined relocatable object has5 exports and no unresolved symbols:
`7d0b354ae26de929f9f84021223cecae6647d95debcd5e234adb6fda44dda875`.
This is not a kernel or flashable artifact.

```powershell
py -3.12 tools/audit_pcie_root_sources.py --linux-repository /path/to/tb322fc-linux-kernel --output /new/root-audit
py -3.12 tools/test_pcie_root.py --wsl-distro Ubuntu --output C:/Users/Public/root-test
```

```sh
python3 tools/build_pcie_root.py --llvm /path/to/llvm/bin --output /new/root-native
```

Evidence: [root component record](../../docs/evidence/pcie-root-20261116.json).
Workbench `lab/records/pcie-root-20261116/{host2,source-audit1}`, native copies
`edl_work/pcie-root-20261116/native1`; Mac `lab/pcie-root-20261116/native1`.
Next connect real platform admission/PHY rails/NoC votes and mappings, then
BAR/DMA/MSI/MHI and whole-kernel recovery verification. Charging remains
incomplete; no device controls, current boot image or GPU worktree changed.

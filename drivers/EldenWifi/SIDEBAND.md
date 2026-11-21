# TB322FC WLAN sideband initialization

The first sideband candidate stopped before radio power: GPIO18 and GPIO19
were `ctl=1/io=0/irq=742`, while GPIO202 was `801/0/742`. The helper rejected
the remote eGPIO state without writing any pin. The complete stock Android,
root, green verified state and original settings were restored.

The exact Armada TB322FC source pin is
`h0cheung/tb322fc-linux-kernel@6f97250ead155fc3b980856323e99a4623dae73d`.
Its `sm8750-lenovo-elden.dts` selects GPIO18 `wcn_sw_ctrl`, GPIO19 `wcn_sw`
and GPIO202 `gpio`, output low, 4 mA, pull down. `pinctrl-sm8750.c` defines
eGPIO presence at bit 11 and AP ownership at bit 12.
`pinctrl-msm.c:msm_pinmux_set_mux` sets bit 12 when selecting a local function
on an eGPIO-capable pin. This explains the original Android observation that
GPIO202 is a local output, rather than a reason to accept arbitrary remote pins.

`SidebandPins.h` accepts the additional remote state only for GPIO202 and only
when all three words equal `801/0/742`. It writes the low output latch before
enabling output, then expects control `1a41` and low input/output readback.
GPIO18/19 remain inputs; only their mux changes to function 1. Every initial
read and guard runs before any write. Unknown mux, active IRQ and any other
remote state are refused. Partial failures retain ownership to reset.

`SidebandSource.py` inserts this initialization into the shared WCN native
provider before radio votes and enable. It checks that Bluetooth and WLAN are
off. It does not modify CE rings, WMI commands, credits, firmware, timeouts or
charger controls. The kernel builder verifies the actual loaded
`WcnPowerNative.o` member against its component report.

The current candidate passed 27 actual-helper ASan/UBSan model scenarios,
including the observed eGPIO state and three near-state rejections, and 61
component qualification cases. Full native/kernel linking, the 30 retained
Apple executable regions, entry delta 7124, asset closure and stock AVB floor
1738713600/footer 0/parent 3 also passed. MMIO remains modeled in the host
tests. This is not hardware Wi-Fi acceptance.

Build evidence is retained in workbench
`edl_work/wifi-sideband-20261120/{host2,battery2,kernel2,entry2,package2}` and
the corresponding macOS lab directories. The actual component commands and
input hashes are in `battery2/result.json` and `kernel2/result.json`.
The signed image is
`2447dfd258f87c6962a24ba4d4293270e3d15b911fe44eb9ecf62175a403729d`,
session `a600174c63405fec`.

[Candidate evidence](../../docs/evidence/wifi-sideband-egpio-20261120.json).
The next hardware capture must verify all three pin readbacks, CE3 state
through the first PMF command, WMI completions and real scan results, followed
by the physical return and complete stock restoration. Association, DHCP and
bidirectional traffic are still required before calling Wi-Fi usable.

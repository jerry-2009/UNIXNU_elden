# Native root worker and v157 kernel

The root controller now has a native worker, real MMIO mappings, GPIO102/103
PERST/CLKREQ access, the shared GCC owner, provisional WLAN power/NoC calls and
shutdown handling. These pieces are linked into a complete derivative of v156.
**The kernel is not packaged/signed or tested on hardware yet. Do not flash the
raw kernel.** BAR/DMA/MSI/MHI and Wi-Fi networking remain unfinished.

## Admission, mapping and lifetime

All three explicit intents are required before a thread is even queued:
`elden-pcie-root=1`, `elden-wlan-power=1`, `elden-pcie-full-on=1`.
`elden-pcie-gen` accepts1–3, default3. Full-on remains a diagnostic budget.
The worker waits for the existing recovery/RPC, fresh charge and5–38°C battery
gates, with at least120 seconds left before starting; transport epoch is pinned.

Seven windows use the source-checked Root base/length helpers. GCC maps0x80000
bytes, covering the6b/6c registers that the older Bluetooth0x60000 window does
not. Two GPIO pages map102/103 atf166000, and a separate read-only observer maps
WLAN GPIO16 atf110000. Mapping failures identify the window and stop before
controls; a context that starts hardware remains until platform reset.

Before acquiring WLAN power the GPIO16 observer must be low: an unknown active
boot consumer is not reset. PERST uses GPIO/2mA/pulldown/output, CLKREQ uses
function1/2mA/pullup/input, matching the exact SM8750 pinctrl/DTS. The native pin
helper preserves unrelated bits and refuses active IRQs, foreign eGPIO ownership,
unexpected muxes and readback errors. It never accesses WAKE GPIO104.

`NativeRuntime.inc` calls the actual root/PHY and WLAN power providers. It does
not substitute successful callbacks for them. Every GCC write requires the
existing `sm8750_gcc_vote_owner` word, with owner50434945; it does not introduce
a second lock. Failed transactions retain uncertain resources and held votes.
One log is emitted per root stage, plus the final IDs/link/result.

## Stop and status

`NativeHookSource.py` adds a strong call to native start at the beginning of
`elden_wcn_power_start`, so the root does not require Bluetooth mode to be enabled.
It adds `elden_pcie_native_stop_begin` before the existing platform stop marker.
These hooks are only selected by the explicit build variant.

The WLAN lease registers the root's quiesce callback. Stop prevents new root
operations, waits within the supplied deadline for the worker to become terminal,
then asserts owned PERST and confirms low state after a measured1ms. It never
reads mutable root fields before the worker finishes. No mapped memory/vote is
freed as a guessed rollback. The current worker never enables endpoint bus master
or creates a DMA window; **this cold-only quiescence must be replaced with actual
MHI/DMA draining before adding DMA operation**.

Status is a terminal-only versioned snapshot; active reads return-11. It records
the last root result and separately records verified stopping. After stop the
returned PERST state is low. It is not evidence that the link remains usable.
Fresh endpoint/Peach-major confirmation and QMI admission are still separate.

## Validation and kernel integration

20 native-worker scenarios/1822 checks pass ASan/UBSan, using the actual runtime,
root and PHY code with the previously used register fixture. Kernel scheduling,
mapping and physical power are modeled. Cases cover requested generations,
all9 mapping failures, disabled intent, pre-start/mid-run stop, unavailable
readiness, competing GCC ownership, pin failure, quiesce timeout and terminal
status. Initial ambiguous one-line indentation was fixed after `-Werror` rejected
it; failed outputs are retained.

ARM64 worker `3aca46110f9cb1407294562576910bcdc37a85d0295c9ab7867d725f2c18cf75`
and hooked WCN `cf3b1b40eef539d32817c6771a1bd4a4d531675f1a6d0f82c04fb4577114f65f`
compile and bind their real providers. Worker has no warning/FP/SIMD/initializer;
WCN retains its one existing conversion warning.

v157 raw kernel:
`36be060cc924399af0a88ab9b9186acd3e63065f9426add12a73835a2edae389`.
Three existing native objects change (WcnPower, WcnPowerNative, ShengUfs), four
root/power objects are added. All core objects/filelist, other archive members,
UFS initializer targets and30 original Apple executable ranges are preserved.
Entry/return still use the original branch and7124-byte relationship.

The UFS replacement retains full pin verification,32-slot owned DMA, IRQ waiting,
automatic Hibern8 and its restoration. It enables AH8 once after pinned-root
verification and removes the already-completed32-cycle diagnostic and its scratch
allocation. No data-authentication gate is removed. Existing26 UFS warnings remain.

Direct branch auditing finds the expected WCN start/stop callers and one call each
to the root transaction and power provider; provider/call instruction bytes remain
unchanged after prelink. [Evidence](../../docs/evidence/pcie-native-20261116.json).

## Reproduce / next action

Run `test_pcie_native.py` with a new output. Build the WCN hooks with
`build_wlan_power_native.py --root-worker` (implies root-power), then run
`build_pcie_native.py --help` for the explicit source-built component inputs.
`build_pcie_root_kernel.py` consumes those outputs plus the verified v156 parent
and original kernelcache; `audit_pcie_kernel_hooks.py` checks the finished pair.
These commands do not flash or require old v99 binaries.

Final Mac build: `lab/pcie-kernel-v157-20261116/build2`; components:
`lab/pcie-native-20261116/{wcn1,native1}`. Workbench mirrors are under corresponding
`edl_work` directories; tests/hooks are in `lab/records/pcie-native-20261116`.
The second build adds complete shared-provider source fingerprints. Its loaded
native sections/commands/symbols match build1 exactly; whole-file differences
are archive build-directory strings in LINKEDIT and the derived PrelinkKCID.
Next prepare the relocated entry, explicit menu and signed boot, audit all assets,
floor and automatic return, then perform one bounded root hardware trial. Current
device image is unchanged; charging and the complete peripheral Goal remain open.

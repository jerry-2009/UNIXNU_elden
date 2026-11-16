# v173 host DMA stop and physical reset proof

The actual platform callback now returns, but the device leaves MHI RESET set
with statusff04. This profile does not reinterpret that state as READY. It keeps
a separate MHI snapshot and requires a host-DMA/physical-reset chain instead.

Only after the real platform callback returned, consumer unbind succeeded and
config errors are clear, the original worker may run `PlatformFence.c`:

1. Read the actual endpoint identity and clear PCI bus-master through the existing
   owned config API; reread command and identity.
2. Read Device Status until transaction-pending is clear within1second. An
   unpopulated zero field is never proof: sampled/idle flags are separate.
3. Mark only host DMA quiescence, then disable/mask the native MSI receiver and
   wait for in-flight handlers. Recheck identity/command/transactions before this.
4. Require those checks and MSI-stopped before asserting the already-owned PERST.
   Read its low latch/input and retain the existing1ms settling/deadline check.
5. Only the successful quiesce callback permits WLAN power release and SMMU stop.

All buffers/maps/tables remain retained until platform reset. This also protects
against late posted traffic. A failed identity, readback, deadline, pending request,
MSI stop or GPIO check refuses power release. The generic MHI warm-reset path
remains unchanged for non-platform/error cleanup. Diagnostics explicitly report
`warm-reset=unverified`; no status whitelist or fabricated protocol success.

The native endpoint's EP-end message remains the cached initial probe; only the
fresh FENCE record and the later physical-reset record establish shutdown.
Host tests execute actual Config, PlatformFence, Msi, Pins and native helpers:
26 scenarios/224 checks with injected IO/callback/transaction/MSI/PERST failures
pass ASan/UBSan. Physical hardware and callback claims are modeled in those tests.

Build `tools/build_platform_fence.py`, then supply its output using
`build_pcie_native.py --platform-fence-build <path>` with the existing qualified
v172 runtime and other providers. The complete root builder adds one object
(148added total) and selects this profile. No runtime firmware/clock/power policy
is changed. Source187 pins, Apple30, entry7124 and27 direct call targets pass.

Mac/workbench `wifi-fence-v173-20261116/{source1,host1,fence1,native1,kernel1}`.
Kernel `f0771691887fced6a21ae6357b659560414bcbeacee2540a9a2896c89339a5d0`.
[Evidence](../../docs/evidence/wifi-fence-v173-20261116.json).
Actual hardware shutdown and the full peripheral Goal are not yet accepted.

Signed candidate `23ade412dae130f6377c83ff6248a77c4e6d3dc181bd8df8336f107fc3357b26`, session `2a72f6a2ab45140f`.
All187 source inputs match Git index; entry/asset/FAT/AVB checks pass
(1738713600/0/3). Hardware validation pending.

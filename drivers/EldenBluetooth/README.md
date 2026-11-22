# Elden Bluetooth firmware adapter

[v99 runtime candidate](../../profiles/v99-bt-runtime/README.md) now packages
the helper, original-job preservation and exact-CDHash stream fixup into a
signed offline boot. Full image/entry-relocation checks pass. It selects real
WCN mode4 and is not a read-only probe; no device run has occurred. Native
initialization, pairing, active sleep and original-job lifecycle remain pending.

[v98 bootstrap preparation](../../profiles/v98-bt-bootstrap/README.md) now adds
the read-only, hardware-derived status and signed arm64/iOS17 BlueTool service.
The exact original21H461 message ABI and optional address format are verified;
the original daemon is unchanged.74 protocol cases and full static kernel
checks pass. Runtime/trust/launchd installation, native routing, pairing and
active sleep are pending; the tablet has not been accessed.

The follow-up [v97-wcn profile](../../profiles/v97-wcn/README.md) now rebuilds
the full19-object stack and links startup/stop into v94. Its native/prelinked
calls, shared owners, five unique firmware payloads and30 original Apple text
ranges pass static checks. It is an unsigned, unbooted kernel; hardware, native
daemon and pairing remain pending. Earlier pending-link notes below are history.

Latest offline change: [WCN shutdown](../../docs/WCN-SHUTDOWN.md) connects the
native radio worker to the maintained recovery template, revokes new UART
work on stop, and exits the host even under socket backpressure.17 UART and12
bridge host scenarios plus two ARM64 scalar object builds pass. Full kernel
link/recovery-hook qualification and hardware remain pending; existing boot
candidates are unchanged. This is not radio, pairing or system-sleep acceptance.

Adapts sheng VFS loading to TB322FC WCN7861 with exactly the five Armada firmware paths.
Runtime APIs sheng_bt_firmware_read/release remain intact. Uses the qualified Elden RAM Data readiness
instead of the GPU addon gate. No startup or HCI download occurs from this archive by itself.
Source: UniXNU-sheng68940017, BSD-2-Clause-Patent. XNU21H461 VFS compile context is required.
Firmware integrity is checked in the staging manifest; live transport and per-device BD_ADDR remain unqualified.

## WCN7861 peripheral protocol

`Wcn7861Peripheral.c` is the board-specific pre-HCI codec adapted from the Armada
TB322FC patch0227 and h0cheung dc7d14/ac6ae99. It validates the entire peripheral
patch/NVM/TME-L container before generating any243-byte download segments. NVM
tag17 second byte becomes8Mbps code0x15; tag27 second byte gets IBS bit0. Only
outgoing copies change, preserving the original firmware files.

The actual Peach20 TME-L asset is ELF32 little-endian RISC-V (machine243). The
codec checks its program-header/file bounds; the board firmware manifest still
has to verify its exact SHA. Control/version/completion/notification codecs
keep peripheral0x31/0x34 separate from ordinary HCI. The four known Peach tuples
use the current UART baud and skip a second ordinary0xfc48 switch.

These helpers contain no transport/startup or automatic initializer. The future
QcaBluetooth adapter must own UART framing, clocks/power, serialized commands,
timeouts and asynchronous notifications. Quarantine a timed-out transaction:
the protocol has no nonce to identify a delayed reply. Ordinary WCN7861 HCI TLV,
the8Mbps GENI resource plan and native iOS17 integration remain to be connected.

Host test `TestWcn7861Peripheral.c` uses the three exact firmware assets and checks
immutable full-file segmentation, malformed late tags/ELF bounds, short outputs,
subsystem/tuple matching and notifications. Compile it only for host tests,
never include its main in a kernel archive. The C codec is GPL-2.0-only; the
public header and existing VFS adapter are BSD-2-Clause-Patent.

## Ordinary HCI continuation

Wcn7861Hci continues the same ready peripheral session without resetting its
H4 framer or dropping queued bytes. Full patch/NVM preflight precedes ownership.
Canonical Pagani EDL encoding sends 243-byte chunks, waits only for the final
patch reply and waits for every NVM reply. Tag17[1], tag27[1] and tag2 change
only in transmitted copies. WCN7861 does not use the older tag17[0] IBS edit.

The executor checks real unified Command Complete, Reset, post-patch ROM/SOC/
patch version, Qualcomm manufacturer and Read_BD_ADDR. A qualified unique
address is required; the shared firmware default is refused. Unexpected,
partial or duplicate completion, short/uncertain writes and timeout poison
the session. There is no retry. Only a physically qualified reset permits a
fresh instance. The transport write must drain the full packet and honor CTS.

TestWcn7861Hci reuses the peripheral controller fixture, then checks the
complete five-asset transition in21 host scenarios. This is model evidence.
ELDEN_BLUETOOTH_HCI_BUILD links the executor and adds both normal assets to
the read-only preflight inspector; it does not invoke startup. Physical power/
UART, native21H461 bluetoothd/UART.SK and persistent pairing remain pending.

## Wi-Fi candidate coexistence

The Wi-Fi network-17 candidate previously selected `mode=0` for the WCN worker,
so Bluetooth disappearing from Settings was a candidate boot-policy result. The
radio-only admission path now records a shared WCN owner and adds the
freshness-only `elden_wifi_battery_available` gate. A qualified network
candidate may append `elden-wcn-power=4` exactly once. This does not claim that
Bluetooth discovery or pairing passed on Elden hardware. Those still require
one combined hardware window.

## HCI completion envelope correction (2026-11-11)

The native bridge build now uses `BridgeCompletion.py` to apply a narrow,
SHA-bound correction to the frozen Pagani-derived `BtBridge.c`. A completed H4
frame can still contain a short HCI command response. Missing status for Reset
or Write Default Erroneous Data Reporting must not clear the reset transaction
or falsely mark native initialization ready. Those malformed responses, short
Command Complete headers and short Command Status envelopes stop the session.
Opcode-zero credit notifications and normal fragmented transport remain valid;
other command return parameters are left to their native consumer.

The old false-ready case was reproduced. The actual fixed bridge passes eleven
ASan/UBSan scenarios and compiles as an ARM64/iOS17 object with unchanged exports
and no FP/SIMD. No firmware, power, clocks, daemon text or hardware state changed.
The fix is wired into the next explicit native Bluetooth build, but is not in
the old v77 UI candidate and has not been linked into a new boot image or tested on
the controller. See the paired workbench's `lab/records/bt-completion-20261111/`.

## UART14 native backend

UartPlatform/UartBackend implement the actual fixed-board register callbacks
and1x8 FIFO packing, real TX completion, bounded failures and resource return.
The epoch-bound shared WCN power/reset/parent provider must grant access.
Default provider returns-EAGAIN/0; no worker invokes the backend automatically.
This is the internal Bluetooth UART, while PC logging remains DWC3 USB.

15 timed hardware-model scenarios include the full five-asset protocol over
ordinary/DFS clocks, small RX reads, CTS and counter-stall/error cleanup.
Native iOS17 build/link and independent original module/HID/assets/signature
checks pass. Actual hardware/throughput, strong power owner, IRQ/DMA and native
daemon remain required; see docs/WCN-UART-20261108.md.

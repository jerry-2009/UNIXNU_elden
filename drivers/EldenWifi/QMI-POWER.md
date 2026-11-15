# Linux QMI → native WLAN power

The exact Peach `pwrseq_qcom_wcn_set_ol_cpr` callback now has a real bridge to
the native WLAN owner. The bridge and the unchanged125-object Wi-Fi runtime,
WcnPowerNative and WcnPower pass a128-object **relocatable link**. This is not
a whole XNU kernel, a boot candidate, PCIe bring-up or Wi-Fi acceptance.

## Contract

The provider declaration comes from the exact prepared Linux header
`include/linux/pwrseq/qcom_wcn.h`, SHA256
`09d5313e43cdcc0a57426d5aea26e25aea8a124411440c4cf3dd29a675319a1a`.
It is part of the frozen TB322FC Peach backport and matches the original board
power-sequencing source. Compile-time assertions require48-byte entries,
32-byte pin names, offsets32/36/40/44 for the four u32 fields and at most16 items.
No Linux `struct device` is cast to an IOKit object or dereferenced by the bridge.

The native PCIe/MHI glue must:

1. Verify the actual endpoint and obtain a native WLAN lease via `WlanPower.h`.
2. Call `elden_wlan_qmi_bind(ab->dev, provider, epoch)` using the actual Linux
   consumer instance before the firmware capability/QMI OL-CPR path.
3. During quiesce, drain QMI requests and call the exact matching `unbind`
   within its supplied deadline before certifying DMA stopped. Contention
   returns `-11`; a caller must never report successful quiescence while a
   request still owns the binding.

The binding is exclusive and does not replace a different live tuple. Both
bind and every request check the real native power lease. Stop/restart cannot
reuse an old epoch; unbind can retire the exact tuple after lease withdrawal.
The gate serializes request/bind/unbind without spinning or hardware retries.

QMI input is copied to the existing native PMU structure, with an explicit33rd
NUL byte for the fixed32-byte name. Nonzero validity fields retain Linux boolean
semantics. The existing shared provider performs all alias mapping, voltage
adjustment, aggregation and real QMP sending. No arithmetic or power sender is
duplicated. Errors return unchanged: unknown consumer, invalid/stale lease,
bad input, partial QMP failure and terminal Held are not successful completion.

## Validation

`test_qmi_power.py` builds the actual bridge, native helper/export bodies and
shared controller. It uses the byte-exact Linux power header; only primitive
Linux types/kernel services/physical I/O are host fixtures. ASan/UBSan passes
47 combined scenarios/423 checks, including the existing38 native/GPIO cases.
The additional chain covers identity and epoch binding, reentry, invalid counts,
fixed-width nonterminated names,16-item maximum aggregation, nonzero validity
flags, stop/rebind and all8 QMP command failure positions. Command values are
observed at the existing QMP recorder; no fake native-success shim is used.

The production gateway compiles with the same ARM64/iOS17 command, forced shim,
configuration and exact headers as the existing `ath12k_qmi.o`;44 actual inputs
are recorded. Gateway SHA256:
`c39bf6e92c211b6b6610161b9ea0f112f807411e675dd22b2b2c7d6412b8ac01`.
It has3 public symbols, imports the real native check/CPR methods, and has no
FP/SIMD or automatic initializer. Fourteen warnings originate in inherited
`lx_skb.h`/`lx_pci.h` shims; none points at QmiPower.c. These warnings and the
runtime's previously recorded9332 warnings are not globally waived.

All125 existing Wi-Fi objects and456 consumed inputs were rechecked without
recompilation or mutation. `ld -r` successfully combined those objects with the
gateway and the two previously compiled power objects. Defined/imported symbol
sets match their union exactly, with no duplicate definition. The Linux callback,
native WLAN methods and shared CPR provider resolve. The remaining62 imports
belong to kernel/Bluetooth/transport dependencies and are recorded; this does
not substitute for a full kernel link. The bound object is an audit artifact,
not a standalone driver to load or flash.

## Reproduce

```powershell
py -3.12 tools/test_qmi_power.py --wsl-distro Ubuntu --output C:/Users/Public/qmi-power-test
```

On macOS, use existing source-built outputs of `build_wifi_runtime.py`,
`build_wlan_power_native.py` and `build_shared_wcn_cpr.py`:

```sh
python3 tools/build_qmi_power.py --wifi-runtime /path/to/wifi-runtime --wlan-build /path/to/wlan-native --wcn-build /path/to/wcn-core --llvm /path/to/llvm/bin --output /new/qmi-power
```

The compiler depfile/output paths are redirected to the new output; existing
runtime objects, rename map, headers, raw compile records and source remain
unchanged. The original runtime auditor still correctly reports the callback
as an external dependency of its125-object set. The separate binding report
proves its resolution rather than weakening that auditor.

Evidence: [QMI power record](../../docs/evidence/qmi-power-20261115.json).
Mac build: `lab/qmi-power-20261115/build1`; workbench:
`edl_work/qmi-power-20261115/build1` and `lab/records/qmi-power-20261115/host1`.

## Remaining work

The native PCIe/MHI caller is still absent: nobody in the boot candidate invokes
the new bind API yet. Next wire real PCIe/BAR/DMA/MSI and lifecycle callbacks,
then integrate the complete kernel and verify recovery before enabling hardware.
Do not simulate binding/readiness, hide MHI errors, or equate this link with
firmware ready, scanning, association, DHCP or traffic. Charging acceptance
remains incomplete; existing v156/stock images and the GPU worktree are unchanged.

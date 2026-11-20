# OEM UMAC access lifetime

The loaded TB322FC `qca_cld3_peach_v2.ko` and public vendor source
`d50b305f7da9e14715a25120a4ac7b1a4b8b97c3` implement a balanced force-wake
recipe in `hal_api.h` and `hif/src/pcie/if_pci.c`. After initialization,
HAL register offsets at or above `0xfe0` take a real MHI reference, assert
`0x3004`, poll `0x01e04040 == 2`, access the register, release the UMAC
reference, and finally drop the MHI reference. Nested users share the UMAC
vote; the final release clears `0x3004`.

The inherited Linux Peach callbacks only take/drop MHI references. Previous
Elden experiments held UMAC over startup or a WMI command. Those scopes are
different from the OEM register-access contract; none established a stable
Wi-Fi scan. This explicit candidate replaces the startup hold with the
balanced register recipe and preserves the same board owner and opt-in.

Raw accessors retain the original dynamic-window lock/selection/readback
but bypass force-wake so the recipe cannot recurse into itself. Below the
threshold and before initialization the recipe is skipped. A failed handshake
clears only this request, drops its successfully acquired MHI reference, and
refuses the requested MMIO. It latches the failure for this binding instead
of repeating polls on every access; owned resources remain for physical reset.
The inherited public read ABI has no error output, so refusal returns all ones.

This is a bounded diagnostic adaptation, not a declaration of the CE3 root
cause. All MHI/MMIO/executor timing in host tests is modeled. Register values,
poll interval/count, shadow/CE configuration, WMI credits, firmware and the
physical return path are unchanged. The startup `umac_hold_trial` profile
bit still selects the existing owner/worker pair; `umac_register_trial` now
qualifies the changed lifetime explicitly.

`tools/build_wifi_umac_register_access.py` consumes a qualified posted-reset
runtime via `--runtime-build`, `--parent-build`, `--llvm`, and a fresh `--output`.
It recompiles one PCI unit and retains124 runtime objects. The boot qualifier
regenerates the exact helper/accessor patch and checks its actual source/object.
`tools/test_wifi_umac_register_access.py` accepts `--cc`, `--pci-source`, and
a fresh `--output`. Its actual-helper scenarios cover balanced calls, nested
votes, skip conditions, MHI failure, UMAC timeout/all-ones, latched refusal,
active-unbind refusal and mismatched owner/controller.

See [signed evidence](../../../docs/evidence/wifi-umac-register-20261120.json).

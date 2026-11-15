# v157 PCIe root trial

The signed root-only trial passed on TB322FC: Gen3 ×2, correct root/endpoint IDs,
endpoint bus-master disabled, followed by sync return and complete stock restoration.
Follow [native worker and build details](../../drivers/EldenPcie/NATIVE.md).

Kernel SHA256: `36be060cc924399af0a88ab9b9186acd3e63065f9426add12a73835a2edae389`.

Signed image SHA256: `f717f7a56323f709724d57aa062fd76ff83afcba5b849508b1fb6c9a0bd98eaa`.
Session: `0b8c9da91e696299`. See [scope and evidence](HARDWARE.md).

`tools/pcie_root_boot.py` qualifies the root build through the existing
`build_v91_boot.py --wcn-report <root-build/result.json> --bt-runtime <root-build/runtime>`
entrypoint. Supply the source-built FD, loader, Data, icon helper and declared
stock/signing inputs as for the v156 parent. Before packaging, use
`prepare_v91_entry.py` on the raw kernel with its actual SHA and the original
Apple executable hashes from `profiles/v91/image-build/plan.json`; pass that
entry result to both packaging and `audit_v91_boot.py`. Use `--portable-fat`.
This is a source-built derivative workflow, not a new combined empty-directory
`build_clean.py` invocation. No old v99 binary or temporary script is a source input.

The qualified menu keeps the 8-second countdown and fallback entries, uses 1011
bytes with session substitution, and requires all three explicit root/WLAN/full-on
intents. Bluetooth mode defaults to0; unrelated frame/CPU observers are omitted.
Thermal, charging, watchdog, sync return and AppleKeyStore events remain enabled.

`test_pcie_root_boot.py` checks the menu and rejected intents.
`assess_pcie_root_capture.py --run <capture-dir> --audit <boot/audit.json> --output <new.json>`
checks the full trial including restoration. `test_pcie_root_capture.py` takes the
same run/audit plus a new output directory and retains its rehashed negative cases.

Next: BAR discovery/mapping and Peach-major identity, then SMMU/DMA/MSI/MHI.
Do not repeat the successful root-only trial. Never flash the raw kernel.

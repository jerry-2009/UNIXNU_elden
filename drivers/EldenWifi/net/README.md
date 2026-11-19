# Elden iOS17 network bridge

This is the BSD/IOKit part of Wi-Fi: real en0, Apple80211 requests, station
events, Ethernet packets and BPF for DHCP. It consumes the existing Ath12kWifi
station API. It does not replace the WLAN/PCIe/SMMU/MSI/CE/WMI/firmware layers.

The donor is the **hardware-recorded iPadOS17/21H461** Sheng implementation at
`08cde20edc3254ed6f7df8d0f5384fb887786e8f`, preserved byte-for-byte in `upstream17/`.
Sheng's `porting.toml` at that revision records firmware c7-00108, WPA2-Personal
on 5GHz/80MHz, DHCP within31s and approximately12/24Mbit/s down/up. These are
Sheng observations, not Elden results. The exact Ath12kWifi ABI is pinned to
`5f7f5a8a9f02f7ab45ed10a2f226e348c519a838`. The newer-OS draft elsewhere in this
directory remains separate and is not consumed by these tools.

`Net17Source.py` retains the proven request/event layouts and chained mbuf
receive path. Its Elden deltas use the original factory identity, keep payloads
and network identifiers out of logging, validate request sizes, propagate
queue refusal and map radio power to the real station API. It does not start an
extra background thread or automatically read network credentials. Inputs are
accepted only while the retained native owner admits the active epoch.

`NetCall` counts accepted callbacks. Stop closes admission; the original worker
waits at most100ms for those callbacks before its unchanged physical-fence
shutdown. Failed drain refuses completion. The interface, callbacks and IOKit
objects remain retained through the bounded platform reset; no asynchronous
ifnet-detach or unload completion is claimed. This also preserves the original
late OSMetaClass registration protocol for the four compatibility classes.

## Validation and current limits

The final host test executes the generated bridge itself: **54 checks** cover
power, real request sizes, scan result iteration, PMK/passphrase conversion,
association/link events, malformed/refused requests, fragmented receive/transmit
buffers, allocation/copy refusal and stop during a live callback. ASan/UBSan pass;
kernel and station services are modeled.

The bridge and worker compile for arm64/iOS17. The bridge has0 compiler warnings;
the worker retains the original1 shadow warning. All imports resolve to the
actual native baseline or the paired provider. Late-init processing removes
only the initializer section and exports the actual initializer symbol.
Full native link and prelink preserve core files, hardware/runtime members and
30 original Apple executable regions. Eight qualification mutations are rejected.
The signed independent candidate passes entry, FAT/assets, session and AVB checks
at1738713600/footer0/parent3, with default xnu and an8s countdown.

See [current evidence](../../../docs/evidence/wifi-network17-20261119.json).
One live trial now proves en0 publication, IONetworkStack opening and actual
Apple80211 requests. Net drain0 and the original physical-fence/full stock
Android restoration pass. It still reports30 WMI timeouts, no accepted scan/BSS,
association, DHCP or traffic. This is **not Elden networking acceptance**. v190's first WMI timeout remains unresolved; no guessed
credit, clock or pdev changes are introduced here. GPU and other worktrees stay
separate. The full peripheral Goal remains active.

## Source build

Use the macOS environment and declared original inputs in
[CLEAN-BUILD.md](../../../docs/CLEAN-BUILD.md). `base` is an output produced from
source by the maintained clean builder; `service` and `worker` are the
source-built service-scan outputs from
[the service profile](../../../profiles/wifi-service-scan/README.md). The parent
identity is checked, not inferred from a directory name. Caller paths are explicit.

```sh
.venv/bin/python -B tools/test_wifi_net17.py \
  --cc /path/to/clang++ --output out/net17-host
.venv/bin/python -B tools/build_wifi_net17.py \
  --clean-build /path/to/base --reference-kernel /path/to/service/native.macho \
  --llvm /path/to/llvm/bin --output out/net17
.venv/bin/python -B tools/build_wifi_net17_native.py \
  --parent-native /path/to/worker --net-build out/net17 \
  --reference-kernel /path/to/service/native.macho --clean-build /path/to/base \
  --llvm /path/to/llvm/bin --output out/net17-worker
.venv/bin/python -B tools/build_wifi_net17_kernel.py \
  --parent-build /path/to/service --worker-build out/net17-worker \
  --net-build out/net17 --clean-build /path/to/base \
  --original-kernelcache /path/to/original-kernelcache --output out/net17-kernel
.venv/bin/python -B tools/test_wifi_net17_qualification.py \
  --report out/net17-kernel/result.json --output out/net17-qualification.json
```

The network build extends the captured strict overlay with the reconstructed
public XNU header namespaces, including the export layout of Skywalk headers.
The original source reconstruction and fixed compiler/header inputs remain
required. No header is pulled from a reference checkout at compile time.

Use `prepare_v91_entry.py`, `build_v91_boot.py --wcn-report ... --bt-runtime ...`
and `audit_v91_boot.py` for this exact profile. `wifi_network17_boot.py` validates
both objects and the preserved service/hardware declarations before the shared
asset, entry and original-executable checks. The individual component, native,
entry, package and audit stages have run; a new single empty-output full Wi-Fi
build has not run. Hardware testing retains fresh battery, serial-bound logging,
full write/readback and complete stock Android restoration.

# Prepare authentication before association

The actual previous adapter starts the station once PROFILE is enqueued,
without a reply from the helper. The fixed donor helper postpones PMK
derivation for a menu PROFILE until the matching LINK. Y700's last full
capture received four message1 frames before submitting all four message2
replies; completion/ACK/keys/port remain0. This ordering does not by itself
prove the missing TX completion is caused by crypto latency.

The preparation race is independently reproducible in the actual adapter:
enqueue PROFILE, call its station turn, and it begins association despite
no helper acknowledgment. The successful donor's file-profile path prepares
the same PMK before connecting its port. The current Elden extension makes
that ordering explicit for the privileged menu/profile channel.

`ProfileReadySource.py` derives the exact already-tested OEM station and
helper sources. It runs the unchanged CommonCrypto PBKDF2 on PROFILE before
LINK, then sends opcode21 with generation/status only. The kernel accepts
status0 only from the current socket session for the current offered profile
and generation. An enqueue is not preparation: both successful enqueue and
actual acknowledgment are needed before the original station machine starts.
Wrong/closed session, stale generation, malformed size and failure status
cannot arm association. A failed enqueue withdraws even a synchronous reply.
Socket closure and profile replacement revoke readiness.

This does not authorize the BSD port or install a key. PTK, replay, MIC, RSN,
AES unwrap, real key completion and group-key ordering remain the donor's
original behavior. No PMK/key/nonce/frame/SSID/BSSID is logged or sent in
the acknowledgment. The private profile remains an external build input.
The real VDEV_START response's nine leading metadata words are observed to
compare physical MAC selection; no register, bank, power, credit or timeout
is altered. OEM command envelopes and physical return remain the prior ones.

Build entry points:

```text
python tools/build_wifi_station_ready.py --parent-build TESTED_OEM_RUNTIME --llvm LLVM_BIN --output NEW_RUNTIME
python tools/build_wifi_station_ready_assets.py --base-runtime STATION_ASSETS --clang CLANG --output NEW_ASSETS
python tools/build_wifi_station_core.py --parent-kernel TESTED_SCAN_KERNEL --assets NEW_ASSETS --clean-build CLEAN --llvm LLVM_BIN --output NEW_CORE
python tools/build_wifi_station_kernel.py --parent-build TESTED_SCAN_KERNEL --runtime-build NEW_RUNTIME --native-build STATION_WORKER --core-build NEW_CORE --assets NEW_ASSETS --clean-build CLEAN --original-kernelcache ORIGINAL_21H461 --output NEW_KERNEL
python tools/test_wifi_station_qualification.py --report NEW_KERNEL/result.json --output QUALIFICATION.json
```

`TestProfileReady.cpp` runs the old real adapter to prove premature start,
then the new actual adapter for success, stale/failed/malformed replies,
reconnect and enqueue/ACK races under ASan/UBSan. `TestProfileHelper.c`
prepares actual CommonCrypto PMK against the IEEE vector before any LINK,
checks repeated/changed/open/invalid profiles, and runs the donor's complete
crypto/replay/MIC/RSN/group-rekey self-test. The original donor blobs are
unchanged; the helper control flow changes, so `crypto_source_unchanged`
is explicitly false while the crypto algorithms remain exact.

Final prepared output is runtime2/assets2/core2/kernel2. Earlier builds
retain their hashes; the initial host harness selected a same-directory
Station.cpp rather than the requested generated file and was corrected to
an explicit source macro before signing. Twenty malformed full composition
cases, scalar ARM64, Apple30 and entry7124 pass. Host/XNU services and MMIO
are modeled; this is not hardware WPA2/DHCP/traffic acceptance. Current Wi-Fi
build still uses explicit prior objects; foundation clean build and this
incremental composition have separate reproducibility scope.

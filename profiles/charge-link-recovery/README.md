# Charging policy recovery after a broken link

The v140 policy can leave manual charging inhibit active if SET28=0 was queued
or acknowledged, but the link failed before bypass readback completed. Its
`applied_mode` still describes the earlier mode. Selecting stock, 80%, or 40–60%
after reconnect could therefore skip the release and prevent later charging.

`drivers/EldenPmicGlink/LinkSource.py` derives a separate policy and private state
header from the unchanged v139/v140 inputs. It records possible manual inhibit
when preparing SET28=0, retains that fact across link loss and unsuccessful
responses, and clears it only after a valid successful SET28=1 ACK. A send
refused before queue insertion restores the previous ownership fact. The real
`adspSend()` returns errors before inserting a message; zero means queued, not
successful DSP execution.

The current source cancels a bypass request when PMIC GLINK loses its epoch.
On reconnect it restores the original automatic window and releases any
manual inhibit the prior request may have applied. This runs even if the
host cannot send a cleanup RPC. A new bypass request requires fresh telemetry
from the new epoch. A request still queued on the old epoch is discarded.

Normal/EU window selection and hysteresis remain owned by the original firmware.
The policy still requires the existing fresh complete readback before publishing
an applied mode. An effective charging value of zero after release can be a
firmware threshold hold. This change does not choose between USB inputs or
establish physical system-power bypass.

## Validation

The actual old C policy reproduces the partial-inhibit defect in a 24-scenario
reconnect suite. The derived C policy passes 30 scenarios, including send refusal,
loss before ACK or readback, malformed/error responses, timeout, failed release,
reconnect, and retained firmware threshold ownership. Existing 18 window scenarios
and 146 policy checks also pass with ASan/UBSan and warnings treated as errors.
The firmware peer is a model of the audited OEM contract, not DSP execution.

Both PmicClient and ChargePolicy have been recompiled for arm64/iOS17 using the
same generated state header through both frozen VFS aliases. The native linker
and full prelink pass, retain all core objects and 30 original Apple executable
regions, and preserve the 7124-byte entry-return delta. Object compilation emits
no warnings; inherited linker warnings remain in the evidence.

The qualifier rejects an old or missing consumer, a stale state-header alias,
an altered object, or a native identity declaration not bound to its artifact.
The original evidence covers the native build. The subsequent entry, signing
and static audit produced boot SHA-256
`ed063e4be3be281c62cf27d655a21facf0f2e01be0f00a2a1fe3edab0e45fdae`,
session `916665e1c3e24274` and rollback contract `1738713600/0/3`.
The workbench receipt is `edl_work/charge-link-20261119/package-publication.json`.
Hardware acceptance is pending. [Original build evidence](../../docs/evidence/charge-link-recovery-20261119.json)

The updated kernel passed 34 charge reconnect scenarios and both existing
window and policy suites with ASan and UBSan. CiscoMac rebuilt both ARM64
consumers over the existing address17 parent, linked the kernel and verified
the entry derivative. Packaging used a hash-verified PyCryptodome wheel
extracted into the temporary build directory for that invocation. The signed
image `f68f681d` (session `f642cda0d1e652d5`, rollback `1738713600/0/3`) passed
static admission and Windows copy verification. Hardware acceptance is pending.
[Updated build evidence](../../docs/evidence/charge-link-auto-stock-20261122.json)

## Rebuild

Use the declared original inputs and macOS environment in
[CLEAN-BUILD.md](../../docs/CLEAN-BUILD.md). No old v139/v140 objects, Patch path,
or private retained CryptoBin package is required.

```sh
.venv/bin/python -B tools/build_clean.py \
  --variant bluetooth --inputs /path/to/inputs.json \
  --output out/clean-charge-link --target boot --jobs 4 \
  --bt-exit-stack --software-keystore --bluetool-launch \
  --bt-transport-trace --bluetool-lifecycle --bt-registry \
  --bt-helper-trace --bt-process-lifetime --bt-address17 \
  --charge-link-recovery
```

`--charge-link-recovery` implies window handoff and verification. It requires the
qualified Bluetooth/address17 baseline and rejects mixed PD, backlight, CPU, UFS,
translation and 2GiB Data experiments. The full combined empty-output build_clean.py
run passed through all 28 stages. It staged the hash-locked 994-file CryptoBin
release under the exported Mu Platforms/EldenBaseCrypto package path, then built
and independently audited the signed boot. The output was not flashed. Hardware
checks remain pending. See [clean-build evidence](../../docs/evidence/clean-charge-link-20261121.json).
The clean candidate SHA-256 is `89d37ae3c38a1053805a0ecb3c0b90423ace65dddde632204474f6cf6b9a426a`,
session `7825ecbd7e13597e`, rollback `1738713600/0/3`.

For the long-edge PC cable comparison, the host CDC logger accepts
`--reconnect-seconds` with `--charge-sequence`. A broken USB connection ends the
trial. After the same physical USB connection and boot nonce are verified and
the charge controller reports fresh readiness, the logger may issue one stock
restore. If a stock command was already sent, the logger waits for its fresh
confirmation without sending it again. Capture metadata records the trial
interruption and stock restore as separate results. USB CDC disconnect and
the PMIC GLINK transport loss described above are separate events.

For an existing **source-built** address17 parent:

```sh
.venv/bin/python -B tools/build_charge_verification.py \
  --link-recovery --clean-build /path/to/source-built-base \
  --parent-build /path/to/source-built-address17 \
  --original-kernelcache /path/to/original-kernelcache \
  --llvm /path/to/llvm/bin --output out/charge-link
```

Host validation:

```sh
.venv/bin/python -B tools/test_charge_link.py \
  --cc /path/to/clang --output out/charge-link-host
.venv/bin/python -B tools/test_charge_link_qualification.py
```

The output's native contract records its actual loaded sections, commands and
symbols and is bound by full SHA to `native.macho`. It cannot be substituted with
an external pathname. The existing runtime, menu, ADT and trust checks continue.
Full dual-port net charging, physical bypass, threshold cycles, sleep and
persistent settings remain unfinished; the full peripheral Goal stays active.

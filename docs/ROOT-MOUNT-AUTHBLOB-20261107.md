# Root-mount chain: auth blob verified, manifest still open (2026-11-07)

Status: device evidence. The startup+USB candidate advanced from
"could not retrieve system-volume-auth-blob" to a later panic at
`IOKitBSDInit.cpp:984`. This note records the verified mechanism and the
remaining manifest boundary so the next shot is not guessed.

## Verified on device

`system-volume-auth-blob` is the iBoot-forwarded SSV credential. In the
restore IPSW it is `Firmware/<os>.dmg.root_hash`, a 229-byte IM4P file
whose sha384 matches the BuildManifest digest. iBoot unwraps the IM4P
and places the 208-byte payload under `/chosen`. Payload layout seen on
this build: `{u32=2, u32=0, u32=1, u32=32, SHA-256 root hash[32], ...}`.

Injection: append property `system-volume-auth-blob` = IM4P payload
(208 B) to `/device-tree/chosen`, bump the node property count. ADT grew
13768 -> 14012 bytes. The files were fetched with zip range requests
against the Apple CDN (no full IPSW download); three `*.root_hash`
members all verified against BuildManifest sha384.

Device result (`startup-authblob-signed.img`, sha `c264290c…`,
boot `1738713600@0`, delta-flashed to boot_a):

```
import_iboot_forwarded_roothash:3491: importing root hash (basesystem ? 0)...
NativeUfs: SystemOS volume 8B46FE7B-… ready
NativeUfs: OS volume 04769D26-… ready
AMFI: finished: 1 0
Still waiting for root device
panic(cpu0): Failed to mount root device @IOKitBSDInit.cpp:984
```

The previous ENOENT is gone — the blob is consumed. This is verified
hardware progress, not a new failure mode.

## Current panic semantics

`IOKitBSDInit.cpp:984` is the `waitForService(matching)` timeout against
`IOResources` with `IOResourceMatch=('IOBSD','boot-uuid-media')`. Both
APFS volumes publish ("ready"), but no service claims the OS volume as
`boot-uuid-media`, so the loop expires and panics. It is a *wait
timeout*, not a mount error.

On real iOS, apfs.kext publishes `boot-uuid-media` only after validating
roothash + sealed-system manifest (mtree). The roothash path is now
proven; remaining suspects concentrate on the manifest or the SSV steps
after it.

## Manifest transport — three candidate channels (unsettled)

`apfs_extract_root_hash_and_manifest` needs both artefacts. The mtree is
24 MB (`Firmware/044-76040-038.dmg.mtree`, IM4P tag `msys`, sha384
`1a9ff873…` verified vs BuildManifest `Ap,SystemVolumeCanonicalMetadata`)
— too large for a plain DT property. Candidates:

| Channel | Evidence | Sketch |
|---|---|---|
| A. `/chosen/manifest-properties` | iBoot copies im4m MANP properties there; kernel has `panic: failed to get manifest properties`; our node exists but is empty | Add the manifest (or a reference) as a property; 24 MB makes this doubtful without a different encoding |
| B. `/chosen/memory-map` | TrustCache/RAMDisk placeholders already live there; `loadTrustCacheWithExternalManifest` suggests the manifest may ride with the trust cache | Check what `kernel.macho.trustcache` is expected to contain |
| C. `IOAPFSPreBootDevice` / `apfs-preboot-uuid` | `import_iboot_forwarded_roothash` references `IOAPFSPreBootDevice` right after consuming the blob | Real devices keep boot artefacts on the preboot volume; heavier change |

The kernel contains no `Ap,SystemVolumeCanonicalMetadata` string, so if
the DT is used the property name is something else. `handle_fsioc_graft`
has `validate_payload_and_manifest`, meaning the SystemOS graft also
wants a manifest.

## Disassembly anchors (kernel.macho, `__PLK_TEXT_EXEC` VA base
`0xfffffff004920000`, strings in `__PRELINK_TEXT`)

| VA | Contents |
|---|---|
| `0xfffffff00566b4e8` | `import_iboot_forwarded_roothash`: print, `/chosen` lookup of `system-volume-auth-blob` |
| `0xfffffff00566b578` | `apfs_extract_root_hash_and_manifest failed with error` print |
| `0xfffffff00566b6a8/6c4` | `IOAPFSPreBootDevice` reference after successful import |
| `0xfffffff00566b748` | `apfs_extract_root_hash_arm`: `could not retrieve %s from device tree` |
| `0xfffffff0056e24ac` | `handle_eval_rootauth` (FSIOC_KERNEL_ROOTAUTH) |
| `0xfffffff0056e271c` | `handle_eval_roothash` second read of `system-volume-auth-blob` |
| string `0x12acb96` | `/chosen/manifest-properties` (AppleImage4; missing node panics) |
| strings `0x12ad22c/23f` | `boot-manifest-hash` / `apfs-preboot-uuid` `/chosen` names |
| string `0x158f474` | `validate_payload_and_manifest` (graft path) |

## `/chosen` delta vs Pandora (data-a-live, SM8850 real device)

We have: random-seed, dram-*, nvram-*, unique-chip-id, chip-id,
darwinboot-memory-size, text-fixups, osenvironment, crypto-hash-method,
certificate-*-status, effective-production-status-ap,
certificate-security-mode, effective-security-mode-sep,
amfi-only-platform-code(=1), system-volume-auth-blob.

Real devices also carry: `boot-manifest-hash` (48 B), `boot-nonce` (8 B),
`root-matching` (dict), `mix-n-match-prevention-status`,
`effective-security-mode-ap`, `apfs-preboot-uuid`,
`associated-volume-group`, `boot-objects-path`, `image4-supported`,
`debug-enabled`, `firmware-version`, `display-scale`.

Pandora additions worth copying: `mix-n-match-prevention-status=0`,
`effective-security-mode-ap=1`, `protected-data-access=1`,
`amfi-allows-trust-cache-load=0`, and a `BNCH` property (48 zero bytes)
inside `manifest-properties` — iOS16+ AppleImage4 panics with
"failed to read boot nonce hash" without it.

Caution: this kernel has `native_owner_publish_boot_manifest`; after the
root mount succeeds it synthesises its own `boot-manifest-hash`. Do not
pre-inject that name — the owner path skips it by design (status=3).
Adding `BNCH` is harmless.

## Suggested next shot (one change per flash)

1. Add `BNCH` (48 zero bytes) to `/chosen/manifest-properties` and, if
   the ADT allows, the manifest property itself; otherwise investigate
   the trustcache packaging first (`loadTrustCacheWithExternalManifest`
   input contract).
2. Diagnostic only: enable the IOKitBSDInit built-in service-tree dump
   (`kIOLogServiceTree`, IOKitBSDInit.cpp:965-978) so the panic prints
   exactly which link in the `boot-uuid-media` chain is missing.

## Artefacts (private workspace, not committed here)

- `edl_work/authblob-20261107/startup-authblob-signed.img` sha
  `c264290c…`, boot `1738713600@0` — device-run, import verified.
- `edl_work/root-hash-20261107/044-76040-038.dmg.mtree` — 24,102,932 B,
  sha384 `1a9ff87306357f25cbaaca4bf15b3aa1ec98b643e840276a31ef694a7c638426a3f75877ac1c3f787389a74ddc871c08`.
- Screenshots `device-mountroot-panic.jpg`, `device-usbonly-panic.jpg`.
- Zip-range fetch: `research/UniXNU-myron/scripts/unixnu/ipsw.py`
  `RangeFile`; ADT edit helper: `research/UniXNU-Odin3/scripts/d1/adtlib.py`.

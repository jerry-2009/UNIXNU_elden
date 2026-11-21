# v91 firmware reconstruction

This profile reconstructs the DEBUG Pakala firmware using immutable Git objects,
the reviewed Elden overlays and explicitly hashed external Crypto inputs. It
does not copy the caller's dirty sources or old target objects. The source
checkout is not reset. The output directory must be new.

```sh
python3 tools/build_v91_firmware.py \
  --mu-root /path/to/mu_wide_platforms \
  --unixnu-root /path/to/UniXNU \
  --crypto-path /path/to/basecrypto \
  --llvm /path/to/llvm-20/bin \
  --output /path/to/new-firmware-output
```

Use Python 3.12, LLVM 20, macOS developer tools and the Mu BaseTools Python
dependencies. Provide the repositories and initialized submodules at the pins
in `plan.json`; nested pins come from those commits' Git links. No fetch occurs
inside this builder. Current working edits are ignored, not erased. The output
records every exported commit and both build commands.

The historical virtual project path is intentional: it fixes assertion strings
and the CodeView path length, which otherwise alter PE layout. The real build
directory can be elsewhere. Signing keys are not needed to build the FD.
Clang's prefix mapping implies Windows-style file separators for this target;
`-fno-file-reproducible` preserves the historical slash spelling. Four source
units receive their recorded compiler clocks via `SOURCE_DATE_EPOCH`. These
control build banners and constant placement, not AVB rollback indices.

The v91 accepted FD predates the local `Main.c` change that moved `ConnectAll`
after configuration loading. That later change is preserved in the archived
host patch, but is not applied here. Later AdvancedLogDxe/DebugLib overrides are
also outside this profile. The PmicDxe INF now references the exact uppercase
`PmicDxeLA.efi` filename; this changes packaging metadata, not firmware bytes.

Qualifying a rebuilt FD requires the independent structural contract, including
the SEC image, all FVMAIN modules, dependency expressions and file order.
Only explicitly parsed CodeView GUID fields and their enclosing compressed
representation may vary. Matching a module GUID list alone is insufficient.
The raw FD hash need not equal the historical image.

The builder copies only the manifest-hashed CryptoBin package into the temporary
Mu PACKAGES_PATH before invoking BaseTools. The caller's external extraction
is verified but never modified. This keeps the EDK II include inside its normal
package lookup roots and records the staged package manifest beside the build
commands.

Original Qualcomm and Crypto binary dependencies remain pinned external inputs;
this does not claim that proprietary firmware has become open source. Do not
publish additional original firmware or signing material. A successful offline
contract check is not a new hardware acceptance result.

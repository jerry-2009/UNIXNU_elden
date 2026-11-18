# 2GiB sparse Data and actual software KeyStore

The user-operated512MiB Data volume exhausted APFS space, including SpringBoard
and iconservicesagent writes. This profile increases its logical capacity to2GiB
using the existing Sheng/DarwinBoot packed handoff and NativeRamBlock sparse
pages. It remains volatile Data; persistent writable Data is still unfinished.

The core's three and UFS's five size checks are rebuilt together with both checks
in the **actual separately archived EldenKeyEventsGlue.o**. Updating only the UFS
overlay left KeyStore refusing startup in v180/v181. v182 with the real adapter
mounted Data, registered the software KeyStore and reached CRC-verified lockscreen
frames. Settings, live available space, runtime memory growth and longer stability
have not yet been accepted. See [GUI evidence](../../docs/USER-GUI-STORAGE.md).

The earlier v182 audit's `keystore_capacity_updated` field contained the string
`requested_size_mib` because a loop overwrote its boolean. The historical report
is preserved. Current qualification emits literal booleans and rejects incomplete
source closure, altered inherited build reports, seed reports and artifacts.

## Clean build

Use the original inputs and macOS/Xcode environment in
[CLEAN-BUILD.md](../../docs/CLEAN-BUILD.md). This entrypoint creates every stage
inside the new output; it does not require Patch, archived v99/v156/v182 builds
or a developer's external directory.

```sh
python3.12 -B tools/build_clean.py --variant bluetooth --bt-exit-stack \
  --software-keystore --bluetool-launch --bt-transport-trace \
  --bluetool-lifecycle --bt-registry --bt-helper-trace --bt-process-lifetime \
  --bt-address17 --data-capacity-2g --inputs inputs.json --output NEW --target boot --jobs 4
```

`--data-capacity-2g` includes the existing charge/PD/backlight/CPU-observation/UFS
idle prerequisite chain, creates the2048MiB seed, rebuilds the actual KeyStore
adapter, and selects `--expanded-data --keep-packed-data` for packing and audit.
The option is part of resume identity. The default seed remains512MiB. A kernel
target with this option also needs the original OS image to qualify its new seed.
The combined new empty-output command still requires a complete validation run;
component and package validation must not be reported as that full clean run.

APFS allocation metadata varies between newly created seeds. The historical
[seed-contract.json](../data-capacity-2g/seed-contract.json) keeps v182's exact
hashes. Current [layout contract](../data-capacity-2g/seed-layout-contract.json)
fixes the original232 logical entries, UUID,233 raw owners, APFS checks and2GiB
capacity. The packer reconstructs the entire raw digest and repeats raw inode
ownership checks; each new candidate binds its own complete seed hashes.

## Qualified component packaging

For a staged build, run `tools/build_data_capacity_kernel.py --parent-build
<qualified-ufs-idle> --core-build <address17> --keystore-build <software-keystore>
--clean-build <base> --seed-build <seed2g> --original-kernelcache <original>
--llvm <llvm> --output <new-kernel>`. These supplied component outputs must be
qualified; this incremental command alone is not a build from an empty clone.

Then `tools/build_data_capacity_boot.py --kernel-build <new-kernel> --clean-build
<base-with-firmware-and-loader> --seed-build <seed2g> --stock-boot <stock>
--parent-vbmeta <parent> --avbtool <avbtool> --signing-key <key> --llvm <llvm>
--output <new-package>` prepares the entry, packs and independently audits the
signed boot. It never accesses the tablet. Rollback1738713600/footer0/parent3,
all30 original Apple executable regions and entry delta7124 remain required.

`tools/test_data_capacity_boot.py` exercises actual qualification for both
capacity variants and rejection paths. `test_data_key_gate.py` tests the exact
old/new independently compiled KeyStore gate; `test_expanded_data_seed.py` tests
the actual sparse helper and legacy default; `test_packed_data_handoff.py` tests
the pinned DarwinBoot ADT parser and allocation expression. Host models and
build checks are distinct from hardware/GUI acceptance.

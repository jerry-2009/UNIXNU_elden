# v148: bounded CPU governor hardware trial

The explicit `cpu-governor` profile completed native compilation/linking, boot
packaging/audit and one bounded Y700 run after maintenance cleared. It ran90.033s,
processed4092 workload windows and confirmed191 normal transitions plus one
original-level restoration. Final levels were8/0 (1996.8/1017.6MHz table values),
SCMI/error0,423 transfers and a clean owner release. Sampled domain0 levels
included960/1152/1555.2/1996.8MHz; domain1 kept its original ceiling.

This validates the bounded controller, not power savings or daily use. The last10
published battery currents during control had median−191.5mA; the first10 after
restoration had median−127.5mA, both discharge. GUI/workload phases differ, so the
result proves neither a saving nor a causal power penalty. It is not promoted as
an energy-saving default. The next focus is storage attributes and UFS waiting/
queue behavior, not repeated frequency tuning without new evidence.

The first32 display-copy records were23,152,640B each. Before control8 records had
median136.49ms; during control24 had133.82ms. The preceding v146 run had134.08ms
over32 records. These are copy costs, not full frame latency/FPS or a controlled
benchmark. The verified desktop retains the existing white placeholder widgets.
No physical touch or active-governor RPC interruption was tested: the RPC stop
hook ran after the governor had already restored its level and exited.

Image `c0c821a0408345517ae2d80a4a9b799566b0b458b733b5c25291fd6b348aac9c`,
session `a32b069d6e2a7573`, rollback1738713600/footer0/parent3. Capture3736742B,
drop55, no reconnect/discontinuity. PD and backlight restored, the new CPU stop
hook returned clean, synchronized RPC reached physical fastboot, full stock
8b8e72da was restored, and Android/root/green/boot/settings equality passed.
Sleep was requested and all jobs terminated. See [hardware.json](hardware.json).

The native stage is:

```sh
python3 tools/build_charge_verification.py --cpu-governor \
  --clean-build PATH_TO_SOURCE_BUILT_BASE \
  --parent-build PATH_TO_CPU_POWER_OBSERVATION \
  --original-kernelcache PATH_TO_ORIGINAL_KERNELCACHE \
  --llvm LLVM_DIRECTORY --output NEW_OUTPUT
```

The base is a complete build from this repository, not a retained v99 package.
The parent is the qualified v146 CPU observation stage. Full clean builds add
`--cpu-governor` to the existing native17 charging option chain, without explicit
`--cpu-power-observation` or `--pd-gui`; prerequisite stages are selected in order.
The native contract is now recorded after the native checks. Individual stages
and complete packaging ran; the newest combined empty-directory command has not
been repeated. Packing still rejects mismatched or missing native contracts.

Two units change:

- CpuPerfSurvey uses its existing closed compile capture and the SHA-bound
  RuntimeSource, with the frozen SCMI headers and generated upstream policy.
  The only additional export is the governor stop entry; new imports must already
  be defined by the parent kernel.
- ShengUfs uses **current-units** metadata and source-provider files, each checked
  against its digest name and the current source manifest. Both ce63730b recovery
  aliases are replaced with the new header. The translation unit stays unchanged;
  exports, initializer extent/flags and initializer relocation targets must match.

All other archive members and core objects are preserved. Existing WCN, backlight
and PD stop calls must remain. The final native branch must resolve to the new stop
provider, and prelink must preserve caller/provider instruction words, alongside
the existing Apple30/entry checks. Boot qualification independently repeats the
stop linkage and source/policy checks.

The menu is exactly the observation menu with `ecp=2` changed to `ecp=3`;1023-byte
limit, existing59 fixups,6GiB,PD/backlight modes and fallback/recovery settings stay.
No hardware operation follows from generating this menu.

`tools/test_cpu_governor_build.py --output NEW_DIR` passed10 offline checks:
real current-header aliases, rejection of the old v91 header/open/missing mapping,
menu equivalence, and synthetic Mach-O missing/changed stop call/provider rejection.
These source-routing/verifier tests remain distinct from the native build and
hardware trial. The controller162 and runtime16 ASan/UBSan cases also passed
again using the scoped `EldenCpuFreqPolicy.h` name. An initial native build exposed
a collision with an existing `Policy.h`; its failed output is retained, the
generated header was renamed, and conflicting overlay additions are now rejected.
CPU compilation had zero warnings; the26 UFS warning diagnostics match the base
file/text after normalizing line/column numbers. No warning waiver was added.

Final native build: Mac isolated/cpu-governor-v148-2. The earlier failed
cpu-governor-v148 is retained. Workbench evidence lives in
lab/records/cpu-governor-v148-20261115 and the matching edl_work build/live folders.
Do not reuse this short run as active-stop, higher-ceiling, continuous-governor,
full protection-cycle or charging acceptance.

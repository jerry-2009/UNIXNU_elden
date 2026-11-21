# CE3 real HP/TP first-failure diagnostic

This profile combines the qualified v173 physical PCIe/DMA/MSI/PERST return
baseline, real signed service/core/native admission and the new SRNG observer
runtime. It preserves the service scan/session gates and original radio protocol,
credits, clocks and timeouts. It is a diagnostic candidate, not scan/network
acceptance. [Observer design](../../drivers/EldenWifi/SRNG-OBSERVATION.md).

Runtime replaces common HAL and v179 WMI only:5 changed/120 retained C units.
The native worker is rebuilt against that exact binding; its generated service
logic stays unchanged. The kernel builder checks inherited objects/archive
members, imports/exports, all30 original Apple execution ranges and entry delta7124.

The maintained baseline plan relocated WcnPower's exact old source into a frozen
repository file. The builder reverses only that descriptor replacement and
requires the original complete-plan digest; it never accepts unrelated plan
changes. Current shared WcnPower remains untouched. Prior policy hashes are
retained separately in the new report; historical reports are not rewritten.

## Compose and package

Build `tools/build_wifi_srng_trace.py` over BASE and V179 as documented above.
Then run `tools/build_wifi_service_native.py --control-trace --service-scan
--wmi-snapshot-build SRNG --parent-native V173_NATIVE --clean-build CLEAN
--service-core OWNER_CORE --factory-mac PRIVATE_MAC --reference-kernel
V173/native.macho --llvm LLVM --output NEW_NATIVE`.

Run `tools/build_wifi_service_kernel.py --irq-snapshot-build SRNG --parent-build
V173 --service-core OWNER_CORE --service-native NEW_NATIVE --service-assets
ASSETS --clean-build CLEAN --original-kernelcache ORIGINAL --output NEW_KERNEL`.
These are explicitly supplied qualified component outputs. This incremental
recipe alone is not a fresh build of every prerequisite.

`tools/build_wifi_srng_boot.py --kernel-build NEW_KERNEL --clean-build CLEAN
--stock-boot STOCK --parent-vbmeta PARENT --avbtool AVBTOOL --signing-key KEY
--llvm LLVM --output NEW_PACKAGE` prepares the entry and independently packages/
audits the full signed boot. It uses the existing512MiB diagnostic Data seed;
the separately verified2GiB GUI profile is not silently merged into this trial.
The tool performs no device operation. All paths are explicit; no Temp recipe
or fixed developer directory is required by this entrypoint.

The new explicit profile rejects mixed credit/SRNG/native variants, wrong unit
deltas, altered base binding, nonreversible insertions and changed producer/
credit/timeout behavior. `test_wifi_srng_qualification.py` checks these actual
boundaries and the exact provider-relocation rule; host3 separately exercises
16 real observer scenarios with modeled MMIO.

v187 hardware captured both snapshot lines: CE3id67/shadowidx34/off0x984,
target/direct0x1b86400,4 entered/returned notifications and lastHP16. Direct
HIF HP/TP0/0 differs from coherent DMA TP8. Validate window/wakeup/read semantics
before blaming hardware consumption. The early return did not prove complete
native shutdown; typed reset/full stock/Android/root/settings restoration passed.
[Hardware evidence](../../docs/evidence/wifi-srng-v187-hardware-20261118.json).

Complete hardware acceptance
requires both CFG/HP lines before forced RDDM and complete physical stop/return/
stock/root/original settings restoration. Raw HP/TP values are observations;
they do not by themselves prove firmware consumption or credit delivery.

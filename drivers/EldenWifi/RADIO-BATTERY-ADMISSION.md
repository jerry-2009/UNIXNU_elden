# Radio execution independent of charger testing

Two PCI-state candidates were refused before radio startup. Raw battery health
was12 at18--20C; a separate exact-stock Android read reports `Cool`. The charger
policy accepts only raw1, so the PCI root's dependency on charger availability
also prevented a radio test. Newer Linux headers inserted Undervoltage and
shifted these enum values; do not use their numeric mapping for this OEM ABI.

The opt-in radio admission reads only a complete existing PMIC snapshot. It
requires current link/epoch, age below10s, SOC>=40%, both cells>=3.8V, aggregate
and individual temperatures10--35C and bounded gauge agreement. Raw12 is
accepted only up to22C, matching the original observed cool region. Unknown,
warm, hot and fault states remain refused. Charger permission is unchanged.

The PMIC worker publishes under its existing lock. A transport change or expired
deadline invalidates the snapshot; getters verify live link and its generation.
The matched PCI/WCN providers retain thermal, recovery, SMMU, ownership and
physical-return guards and require this real provider before accessing hardware.
The menu explicitly selects `epd=0` to avoid the unrelated PD pulse/suspend
experiment. No output FET, role, OTG, charger mode, firmware or current limit is
forced; ordinary existing SDP policy remains unchanged.

85 actual admission/cache scenarios pass ASan/UBSan, including gauge, health,
age, epoch and ABA-link failures.55 composition mutations and full scalar native,
30 Apple execution-range, entry7124 and signed-boot audits pass. An existing
transcript signed addition retained a UBSan import after inlining changed; the
new generator bounds `snprintf`'s result before addition and preserves that failed
build. The worker also requires the actual provider object, checked again by
the full linker. Host tests model XNU services; hardware is pending.

```text
python tools/test_wifi_battery_admission.py --cc CLANGXX --output NEW_HOST
python tools/build_wifi_battery_admission.py --pmic-build QUALIFIED_PMIC --wcn-build QUALIFIED_WCN --clean-build CLEAN --parent-build SERVICE_KERNEL --llvm LLVM --output BATTERY
python tools/build_wifi_net17_native.py --umac-hold --dma-inspect --battery-only --battery-provider BATTERY/PmicClient.o --parent-native SERVICE_WORKER --net-build NET17 --reference-kernel SERVICE_KERNEL/native.macho --clean-build CLEAN --llvm LLVM --output WORKER
python tools/build_wifi_net17_kernel.py --parent-build SERVICE_KERNEL --worker-build WORKER --net-build NET17 --mac-phy-runtime PCI_OBSERVER --battery-admission-build BATTERY --clean-build CLEAN --original-kernelcache APPLE --output KERNEL
```

[Candidate and exact evidence](../../docs/evidence/wifi-radio-admission-20261120.json).
The new iteration resumes the existing CE3/write/MHI diagnosis, followed by
full stock restoration. Wi-Fi scan, association, DHCP and traffic remain pending.

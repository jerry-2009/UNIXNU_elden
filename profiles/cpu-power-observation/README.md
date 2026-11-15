# v146: eight-core load and two-domain PERF observation

Real hardware captured all72 CPU rows (nine points, eight intervals on each of
eight CPUs) and all18 firmware-level reads. The PC independently recomputed every
qualified load interval from the raw counters and timestamps. Both domains
responded: NCC0 stayed at table level8/1996.8MHz, NCC1 at level0/1017.6MHz. This
resolves the missing second-domain observation from the old single-core v38 run;
it does not prove why that older request was refused.

| CPU | Median busy share over eight intervals |
| --- | ---: |
| 0 | 5.70% |
| 1 | 54.80% |
| 2 | 9.90% |
| 3 | 7.55% |
| 4 | 1.80% |
| 5 | 7.35% |
| 6 | 7.40% |
| 7 | 4.70% |

The window includes a virtual Home action and framebuffer captures while entering
the desktop. These are not steady idle/interactive benchmarks, thread attribution,
instantaneous measured MHz or proof of CPU power consumption. They disprove an
all-core/max-level explanation for this window and supply the first complete
joint load/level evidence for a load-aware governor. Do not blindly lower every
core, and do not enable untested PSCI idle from another port.

PD mode2/thermal3 and normal GUI backlight service6 remained selected, with the
original SDP-only500mA limit and6GiB memory window. CPU code only queries; the
PERF_SET/LIMITS_SET whitelist remains closed.55 SCMI transfers completed, channel
free1/access-error0. Backlight request/readback2048 and restore1597 passed.
The last10 qualified published battery samples had median−147mA; no net-charge
or full protection-cycle acceptance is claimed, and this is not an A/B comparison
with v145. Battery started at100%.

SpringBoard is visible in CRC-checked frames4/6/7 (visually reviewed), with the
existing white placeholders/black background. The watcher matched frames4/5 but
later lost its small Settings template. Its old code incorrectly erased the
already-observed desktop and labelled the bounded return “unproven.” That host
bug is corrected without another device run; the actual old/new frame/deadline
blocks replayed this run and four adjacent cases. Original trial.json is retained.
No Settings tap, physical touch or perfect rendering claim.

Image `57b15d388ba2f60782f3321de5c17e1749420a898ecd7f0c7dfc07c72c8f473a`,
session `f88f55ed2faebab6`, floor1738713600/footer0/parent3. One native object
rebuilt; all core objects, existing archive members, native exports and the30
original Apple executable regions preserved. Native compilation had zero warnings.
23 ASan/UBSan observer cases and428 actual bootarg parser checks passed. Two
numeric-one security flags use equivalent bare spelling, debug0x14e becomes334;
only `ecp=2` changes menu semantics. Fallback entries and deadlines remain.

Capture3606628B/drop25, no discontinuities/reconnections. Synchronized RPC,
physical fastboot, full-SHA stock8b8e72da restore and Android/root/green/boot/settings
equality all passed; sleep requested and all jobs terminal. The standalone boot
stages ran; newest combined empty-directory build was not repeated.

See [source and build instructions](../../drivers/EldenCpuPower/README.md),
[hardware.json](hardware.json) and [validation.json](validation.json).
Workbench: `edl_work/{cpu-power-v146-20261115,live-cpu-power-v146-20261115}` and
`lab/records/cpu-power-v146-20261115`. No retained v99 object is needed; add
`--cpu-power-observation` to the documented clean charging build chain.

# v129 typed BlueTool reply observation

The original owned helper's reply decisions and XPC operations are retained.
Source-derived calls report only phase, script enum, error, state and identity
flag using syscall179. No script contents, address, keys or packet payloads are
logged. Phases1–8 cover parse, status read, decision, fields, os_log return,
peer lookup, send return and release return; scripts1/2/3 mean boot/init/deepsleep.

The actual arm64 emitter passes64 instruction cases at two loads with a syscall
double, verifying argument packing, SP and callee-saved registers. The kernel
observer is bound to the new exact owned CodeDirectory, name and magic, with a
64-marker cap. The precise owner launch exception is updated to that same hash;
the old helper trust module is replaced, not retained. Original Apple/Icon trust
modules and the already verified cache signature remain intact.

Helper SHA5ba171b40cbedeb3eef1f5a3dffc19fba4a84d330377e738a3bf0e32cf78b00a,
CDHashea0063bd7aea0b3dae47df4d1bd9495eba480785. Native signing/target17 checks pass.
One scalar kern_exec object is rebuilt over v128; other objects, registry/cache,
native17 routing and30 Apple executable regions are held. Initial packaging
caught that the consumed payload header was3032579d…, not the older d0e110db…
variant. Explicit consumed-header binding plus final embedded-byte verification
fix that error. The rejected image was never flashed. Final build: helper-trace-v129-2.

Add `--bt-helper-trace` after `--bt-registry` and prerequisites in build_clean.py.
It rebuilds the helper from source and regenerates the payload, exact launch
identity and trust entries; no historical v99 artifact is an input. Full baseline
and appended stages ran separately; combined empty-output build is not rerun.

Hardware: imagebdbf8db59c6e741aaeaebb878c354f24566cd966e2a530f08bf1cdccde8db7ef,
sessionfe9c51f948ea4aaa. All eight phases appear for boot and init, both result0,
Ready state and valid identity. The peer exists and send/release calls return.
Then native H4 connect reaches `client connected pid=79 unit=1` and result0.
This validates marker delivery and crosses the previous observation gap; it does
not prove later packet traffic or pairing. The complete tail records a specific
panic: `Unexpected non zero uu_proc_refcount = 1 @kern_proc.c:500`, followed by
the180-second panic wait and SDAM-directed PSCI reset. NativeHost.connect retained
proc_find's per-thread reference past the callback/system-call boundary.

Physical fastboot recovery and complete stock SHA restoration pass; Android/root/
green/boot completion are observed and sleep requested. This is confirmed panic
recovery, not synchronous RPC recovery. Hardware capture/drop details are in
hardware-result.json. Next fix the process-reference lifetime; do not rework
successful boot/init replies or add a speculative sleep-success bypass.

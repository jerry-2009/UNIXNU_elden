# v130 process-reference lifetime

v129's complete log contains a kernel panic immediately after H4 connect:
`Unexpected non zero uu_proc_refcount = 1 @kern_proc.c:500`. The ARM syscall
return path calls uthread_assert_zero_proc_refcount. NativeHost stored a
proc_find reference in its long-lived context and released it in another callback.
That cannot cross this per-thread reference boundary.

ProcessLifetimeSource derives the fix from the reviewed registry source. The
context stores PID, unique process ID and control unit. connect balances proc_find
before returning; failure clears only the same identity/unit. disconnect clears
only its own unit. Shutdown looks up the process temporarily, verifies uniqueid
before signalling, and releases on the same callback. This prevents PID reuse
from targeting another process. Reference tracking is not disabled.

The actual old callback reproduces refcount1 on successful return in the host
model. Fixed callbacks pass ASan/UBSan success, missing/wrong process, busy,
bridge failures, replacement/unit isolation, shutdown and PID-reuse cases. The
WSL run ended abnormally after compiling the original fixture; the final complete
host run uses Mac Clang (process-host-mac1). Native compilation replaces one
NativeHost archive member, retains the core/other members/exports and30 original
Apple executable regions, and passes entry/menu/asset/AVB audit.

Add `--bt-process-lifetime` after the `--bt-helper-trace` source-build chain.
The standalone tool consumes clean-build and helper-trace outputs, not historical
v99 binaries. Each stage was run; the whole combined empty-output invocation is
not rerun. Helper/script decisions, cache, registry and radio firmware stay fixed.

Hardware: image588cc53c644de5cf5716531d033b29d14ebc85abb0c1e5e3c342fa0920906479,
sessiona07ba677acb41917, floor1738713600/footer0/parent3. No proc-reference panic
is recorded. H4 sends26 packets and delivers25 incoming frames, bad0/pending0;
the native daemon subsequently exits before stack-ready, so pairing remains
unverified. Unlike the prior panic runs, the log continues and session-bound
RESET_AFTER_SYNC succeeds. Full stock SHA recovery and Android/root/green/boot
completion pass; sleep requested. Capture1170810B/drop58, no discontinuity.

Next follow the native daemon's new exit after the command sequence ending in
0x0c33/0x0c31. Its saved stack can be mapped using inferred slide0x426000:
return0x100591e88 corresponds to0x10016be88. This is an inference from matching
call sites, not a measured VM map. Do not reopen the fixed reference bug or
disable global launch constraints to hide the subsequent restart failures.

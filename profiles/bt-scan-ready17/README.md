# v134 publish scan capabilities after discovery

Superseded: v135 observed populated capabilities and applied instructions;
actual native send-path analysis then proved the two lower roles reversed.
See [bt-scan-roles17](../bt-scan-roles17/README.md). Do not reuse the old labels.

Hardware still sends0x200b/status0xc and exits with out50/up49, despite native
completion0/accepted1. The ordering fix alone did not resolve the observed
failure. Do not promote this as a scanning baseline or force capability bits.
Next capture actual native Supported Commands byte37 and the cache/HCI/vendor
flags at completion, distinguishing absent data, later overwrites and routing.
The stock Android HCI snoop directory was empty; no logging/toggle was enabled.

v133 still sent legacy0x200b and exited on status0x0c. Its static setter and
getter tests did not cover configuration before HCI discovery. The upstream
Type0 publisher explicitly refreshes caches after feature discovery. This
profile adds that missing lifecycle update to the exact17 completion path.

After the original completion result is reported, a successful result calls
the existing qualified dynamic scan setter. It rereads real0x2041/0x2042 bits
and publishes the cache/lower flag; a failure leaves both alone. The original
result, comparison, native state2/3 store and context clear are preserved.
No new success or capability is fabricated. The redirection changes only an
exact branch in this adapter's generated zero-padding thunk; original page
comparison remains against the unmodified Apple image.

The table now uses all40 entries of the already-tested bounded parser.
60 instruction cases reproduce the stale-cache ordering in v133, verify the
new update at two slides, cover absent/partial/full command support and native
failure, and check X0/SP/LR/callee registers plus original global state/cleanup.
That reproduces a real software gap; it does not independently prove that this
ordering was the only cause of the observed hardware failure.

Use the full process-lifetime chain from [scan17](../bt-scan17/README.md),
replacing `--bt-scan17` with `--bt-scan-ready17`. All source stages execute
from the declared clean build; no previous v99 runtime is consumed. Individual
stages are tested, while the new combined empty-output command was not rerun.
Hardware results are separate; pairing remains incomplete until verified.

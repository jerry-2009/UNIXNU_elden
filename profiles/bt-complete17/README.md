# v132 native17 completion and optional-command support

Hardware reached `ELDEN_BT_NATIVE_INIT pid=79 result=0 accepted=1`, followed by
the original daemon's `Update Dynamic Store with state On value 1`. H4 increased
to out50/up49. The daemon then exited through a different stack, so discovery
and pairing are still unverified. Capture1172960B/drop31/no discontinuity;
typed sync return and full stock8b8e72da/Android/root/green/boot completion passed.
Image`d8daf82b3ea91f082654cd97fd68bf3027c17255cbe021329061b339b649cf86`,
session`ddec186b47cba937`; all device jobs ended and sleep was requested.

Next: resolve the post-On exit (inferred slide0x480000 maps the first returns
to0x100107bd4/0x100520250/0x100058904). The first is uniquely tied to an imported
`__exit` BL among matching page offsets, with both parent call targets matching.
This is an inferred slide, not a captured mapping. Also preserve the legacy
failed-start-counter reset when a native completion is accepted in the next
candidate; this diagnostic version updates ready flags but does not reset that
counter. Do not treat `ready=1` after client disconnect as a live daemon.

v131's three optional callback changes did not complete initialization on the
tablet: the final H4 count was still out26/up25. The exact original 21H461
submission routine at `0x100050934` also checks Supported Commands before it
sends a packet. Descriptor index `0x7c` at `0x100925dc0 + 24*0x7c` names opcode
`0x0c5b` with support encoding `0x1208`: byte18/bit3 of the real table at
`0x100945820`. An absent bit returns local error `0x274`, without transmitting.

This candidate follows the proven Sheng optional-feature policy while using
the exact iOS17 addresses and original-byte checks. `Native17Completion.py`
includes v131's three callback changes. Its gate at `0x1001840a0` reads the
actual capability bit: a supported command follows the original instruction
stream; an unsupported optional step advances the original chain with its
original context. It does not synthesize an HCI response or modify capabilities.

The original completion at `0x100182be4` receives the final native result.
A bounded diagnostic thunk reports it through syscall179, preserving X0,
callee-saved registers, SP/LR and the displaced comparison. Original state2/3
publication and context clearing still execute. The kernel accepts ready only
for the current PID/uniqueid/control-unit, a live real link, result0, no pending
command/reset/withdrawal/stop. Failures remain failures. The exact daemon name
and original CDHash guard the marker; log limiting does not suppress subsequent
state updates. The earlier real-link `0x0c5b` reply heuristic is removed.

Preparation merges adjacent cave bytes and retains the existing32-rule table
limit. Original identity, page guards, launch constraints, helper/cache/trust,
radio firmware, rollback floor and recovery are preserved. Only two native
objects and two existing core objects are rebuilt. Thirty original Apple
execution regions and the startup assembly contract are checked independently.

Validation:24 original/patched completion/support instruction cases at two
ASLR slides,144 inherited optional-callback cases, plus actual host completion
and marker bodies under ASan/UBSan. External syscall/logging/chain bodies and
kernel primitives are modeled, so these tests do not prove hardware operation.
The host fixture reports two warnings because its weak target is defined in the
same translation unit; native compilation uses separate core/host objects.

From the clean-source entry, select `--bt-complete17` after the documented
`--bt-process-lifetime` chain, without `--bt-optional17` (already included):

```sh
python3 tools/build_clean.py --inputs /path/to/inputs.json --output /path/to/new-build \
  --variant bluetooth --bt-exit-stack --software-keystore --bluetool-launch \
  --bt-transport-trace --bluetool-lifecycle --bt-registry --bt-helper-trace \
  --bt-process-lifetime --bt-complete17
```

The source-built parent and each new stage have executed; the combined command
has not been rerun from an empty directory for this optional stage. Original
daemon bytes are read from the declared OS image, never from a previous v99
runtime. `runtime-report.json` and `native-contract.json` freeze the qualified
table and linked layout. Hardware observations are recorded separately; HCI
transport or ready alone does not prove discovery, pairing, or sleep support.

Publication check: the new builder was normalized from Windows CRLF to Git LF
and its four units were rebuilt in `complete-v132-lf`. The full loaded native
contract is identical to the tested build; whole kernel hashes differ, so no
whole-artifact equivalence is claimed. Entry and portable profile qualification
pass using the canonical LF source hashes. This did not require another device
trial. See [validation evidence](../../docs/evidence/bt-complete17.json).

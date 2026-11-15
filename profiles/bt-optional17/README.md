# v131 optional native17 HCI callbacks

Hardware result: initialization still exited with H4 out26/up25; no native
completion was observed. Capture1178090B/drop25/no discontinuity. Typed sync
return, full stock SHA restore and Android/root/green/boot completion passed.
This is not an initialized-stack baseline. v132 adds the real Supported Commands
gate and native result notification; see [bt-complete17](../bt-complete17/README.md).

The v130 daemon exits through `HCI initialization failed` after the sequence
ending in Host Buffer Size0x0c33 / Set Controller To Host Flow Control0x0c31.
The full original21H461 stack maps to0x10016be88. Its precise controller error
was not recovered from that capture, which reports58 dropped bytes.

QcaBluetooth22ff97f9's proven27 adapter permits rejection of host buffer/host flow
and erroneous-data-reporting features. This maps that policy to three exact17
callback instructions, retaining original daemon identity, replies and rejection
logging. Host flow keeps its original zero-status fast path using CBZ rather
than logging an unsupported feature on successful status. All other callback
bytes and mandatory initialization paths are unchanged. Kernel link/deadline
guards remain active; no controller success or capability reply is fabricated.

| Callback | Instruction VA | Change |
| --- | --- | --- |
| Host buffer size |0x100184c60|Pass0 to the initialization-chain continuation after existing logging|
| Host flow control |0x100184c94|Preserve success; follow existing unsupported-flow continuation on rejection|
| Erroneous data reporting |0x100184d4c|Pass0 to the initialization-chain continuation after existing logging|

Actual original/patched callback instructions pass144 cases at two ASLR slides,
with logging on/off and multiple statuses. Chain arguments, SP and callee-saved
registers are verified; external logging/chain bodies are doubles. This is not
hardware proof. The original byte checks, complete original SHA/UUID and the
existing native17 model patch remain mandatory. Only three page rules are added,
bringing the ADT table to25 (within32); the exact table is compiled into both
runtime and page guard. kern_exec/ubc_subr rebuild scalar; other inputs/exports,
entry and30 original Apple executable regions pass verification.

Clean source entry adds `--bt-optional17` after the process-lifetime chain.
prepare_bt_optional17.py reads the original daemon from the declared OS image
mounted read-only, and builds rules/header/guard from source. All stages have
run individually; the combined empty-output invocation has not been rerun.

The optional0x0c5b support-bitmap skip used in27 is not part of these three callback
changes. Its native immediate-submission failure path and the bridge's current
readiness criterion remain to be evaluated from hardware. Do not call the
full stack initialized solely because an optional error was tolerated.

Image8800207721380a89ed11e19c3f33a1ec2aeaf327b87608dc890d5611e57b2de6,
session23b1a6487db7f35b. Floor1738713600/footer0/parent3, menu, helper, cache and
radio firmware are unchanged. Hardware observations are recorded separately.

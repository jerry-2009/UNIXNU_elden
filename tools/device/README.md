# Maintained device transport tools

The existing AVB admission, Firehose buffering/delta transport, full-image writer
and USB console now live here. The writer requires an explicit `--workbench`;
the console requires an explicit `--output`. Neither stores runtime logs in the
source checkout. The old workbench entrypoints are compatibility launchers.

These tools retain this owner's exact device selection and stock signing-floor
contract. They are not generic flash utilities for a different tablet. Moving
their paths does not authorize a device operation or replace candidate review.
No device was accessed during migration.

Offline example (omit `--write`):

```powershell
py -3.12 tools/device/flash_verified_boot.py --workbench D:\Desktop\Git\Patch\Y700-Elden candidate.img reference.img
```

A live operation still requires independent full SHA, fresh power admission,
verified target/GPT and complete post-write readback. See the current maintenance
state before using it. The writer refuses `--write` while the maintenance marker
exists. Dependencies are Python 3.12, pyserial, pycryptodome and Pillow.

The portable CLI path has changed; transport/control bodies are preserved.
Local model tests cover battery admission, port ownership/readiness, session-bound
commands, framing and reconnect behavior. They do not prove physical USB behavior.

Charge-sequence confirmation requires `charge_control=1`, a valid unsigned32
generation greater than the pre-command value, and the requested mode. Historical
mode/generation values retained during telemetry loss cannot finish the sequence.
If availability, mode or generation ceases to qualify during the observed hold,
the hold restarts after a qualifying sample; the original command is not replayed.
The first confirmation must arrive before45 seconds; an in-time confirmation can
finish its hold afterwards. One bounded stock recovery remains. Recovery errors
stay in the report even if stock later succeeds. Counter
exhaustion stops controls rather than accepting a wrapped generation. These are
host-only changes; `test_charge_sequence.py` covers the failure/success paths.

The v140 candidate still requests `smp-hold=240`; the source helper permits at
most600 seconds and the normal watchdog/recovery path is retained. Do not infer
that a longer PC logging duration extends the target's qualified observation
window. No long charge-cycle candidate was built by this host confirmation fix.

# SPMI page translation survey (v141)

One hardware run completed: SDAM APID586, ADC APID593 and DC APID705 all
returned matching successful read/write translations. DC resolves to
`0x0c7c1010`; all three PAR attribute bytes are0. The same temporary VA was
reused after each mapping release, with the translated PA changing correctly.
This rules out a mismatch in these current mappings, not all possible causes of
the older v61 abort. It does not prove that a downstream DC FIFO write is allowed.
Capture171487B/drop1, synchronized return/full stock restore and Android settings
equality passed; see [hardware.json](hardware.json). The tablet was returned to
Android and sleep requested. No DC write was retried.

This diagnostic distinguishes address/translation permission from downstream
bus rejection after the historical DC FIFO abort. It does not retry that write.
It builds on the v140 charging handoff and the existing Bluetooth/address base.

At the first qualified charge-control availability, the PMIC worker runs once:

1. Read the fixed v7.2 version,896 APID count, PPID and EE0 ownership tables.
2. Find exactly one owned APID each for recovery SDAM0x071, ADC SDAM0x090 and
   historical DC endpoint0x72a. Recheck identity/owner after mapping its page.
3. Apply `AT S1E1R` and `AT S1E1W` to the FIFO virtual address, reading PAR_EL1.
   These walk translation tables; the FIFO address is never dereferenced.
4. Restore the previous PAR_EL1 and interrupt state; release each mapping.

Only core/version/ownership tables are read via MMIO. The survey has no FIFO,
command, PMIC register, owner-table or permission writes. Existing baseline
initialization and recovery still run normally. Translation success must never
be used as authorization for a DC write or described as successful charging.

The native compiler emits exactly one read-translation and one write-translation
sequence, bounded by the two interrupt-state calls, with PAR saved/restored.
The two PMIC objects, all core inputs, original30 Apple executable regions,
entry and full boot/AVB contracts are checked. The current charge policy bytes
remain v140; only this diagnostic's PmicClient derivation adds the survey.

For a clean build, append `--spmi-translation-survey` to the full
[v140 option chain](../charge-window-handoff/README.md#build). It includes window
handoff/verification. Staged builds use `build_charge_verification.py
--window-handoff --translation-survey` with its declared inputs. The variant has
its own native-content contract and exact source derivation check. The individual
stages and full packaging ran; the newest combined empty-output command was not
repeated. This is an opt-in diagnostic, not the daily-use charging default.

Decode a captured session with `tools/analysis/assess_spmi_translation.py`.
It rejects mixed sessions, missing/duplicate endpoints and inconsistent APID/page
arithmetic, and reports raw PAR/attributes separately from bus-write permission.

The Android `1-07` device is under the PMIC GLINK debug proxy. It is not evidence
of an alternate physical bus on which it is safe to retry the old write.

# Portable HIF lifetime

The complete station trial reached authentication/association and EAPOL3RX/
3TX submissions, with0 observed transmit completion, keys0/port closed.
The actual cause of that completion failure remains unproven.

Source comparison found a concrete lifecycle gap: the original Linux core
calls `ath12k_hif_start`, which sets `ATH12K_PCI_FLAG_INIT_DONE`, binds the
per-register UMAC accessor and starts its CE receive/IRQ path. Our portable
callback bypassed that core; its own CE rings scan successfully but never
established that HIF lifetime. The successful Piano donor also holds its real
MHI device wake reference across the runtime and reaches all chip registers
through its checked dynamic window. The protected OEM access helper in this
repository already checks the INIT_DONE gate, owner and real MHI get/put.

`PortableHifPatch.py` restores only the required portable lifetime after the
real OEM firmware mode starts and before its CE/DP programming: exact Peach
identity/MissionMode, INIT_DONE, existing UMAC bind, real `mhi_device_get_sync`
and one owned retained wake reference. It does not start Linux's unused CE
producer rings or completion handlers. Reads/writes continue through the
original checked PCI/UMAC accessor. Failed get is not balanced by a false put;
the owner is retained on failure. The original power-down unbind releases the
reference once, after the portable protocol has stopped, before physical fence.

This is a source-supported missing lifecycle repair, not proof that it caused
the first data-completion failure. No clock/credit/timeout/firmware replacement
or speculative ring reinitialization is included. The tested full station/DP,
WPA2 helper and iOS17 bridge remain unchanged.

Two C objects rebuild,124 runtime objects retained.11 actual helper cases
under ASan/UBSan cover wrong owner/identity/state, bind/get failure, repeated
prepare and correct one-time release; MHI/MMIO are modeled. Full native/
prelink preserves30 Apple executable regions and entry delta7124.12 station
composition mutations and signed package audit pass. PCI120/core157 inherited
warnings remain. This candidate still requires one real functional EAPOL/key/
DHCP/traffic and full return trial.

Image `bb3a7d0e78778a8750fea145fadd410086648698658dbc253f9c43e08a2c1824`,
session `8d353d51bfe5c226`, floor1738713600/footer0/parent3, untested at creation.
Mac/workbench `wifi-station-hif-20261121/{runtime1,kernel1,entry1,package1}`;
helper-host3 is the final SDK-backed verification. This does not repeat the
failed single-register wake-only trials: its test covers the real full station.

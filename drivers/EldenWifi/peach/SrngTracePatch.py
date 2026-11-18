"""Reversible CE3 notification counters and first-WMI-failure real HP/TP reads."""
import hashlib

EXPECTED = {
    "hal.c": "38f5507084d235fb5f5a859ac7cc628915ff6a62d3bcaca93ccec0f37eef2101",
    "wmi.c": "d5ff554c0a800f94a7b25d3af815fa0d0b8b7c3f6b512901f73c39d5c7935963",
}


def patch(name, data):
    if hashlib.sha256(data).hexdigest() != EXPECTED[name]:
        raise ValueError("SRNG source differs: " + name)
    original = data.decode()
    text = original
    changes = []

    def replace(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise ValueError("SRNG anchor differs: " + old[:80])
        text = text.replace(old, new, 1)
        changes.append((old, new))

    if name == "hal.c":
        replace('#include "hif.h"', '#include "hif.h"\n#include "SrngTrace.inc"')
        old = '''\t\t\tath12k_hif_write32(ab,
\t\t\t\t\t   (unsigned long)srng->u.src_ring.hp_addr -
\t\t\t\t\t   (unsigned long)ab->mem,
\t\t\t\t\t   srng->u.src_ring.hp);'''
        replace(old, '\t\t\tesn_enter(ab, srng);\n' + old + '\n\t\t\tesn_exit(srng);')
        start = text.index('void ath12k_hal_srng_shadow_update_hp_tp(')
        end = text.index('\nstatic void ', start)
        block = text[start:end]
        marker = '\tlockdep_assert_held(&srng->lock);'
        if block.count(marker) != 1:
            raise ValueError("Shadow update lock anchor differs")
        replace(block, block.replace(marker, marker + '\n\tesn_timer(srng);', 1))
    else:
        old = '\tif (ret == -EAGAIN)\n\t\tath12k_warn(wmi_ab->ab, "wmi command %d timeout\\n", cmd_id);'
        replace(old, '\tif (ret == -EAGAIN) {\n\t\telden_wifi_srng_first_wmi(wmi_ab->ab);\n' +
                '\t\tath12k_warn(wmi_ab->ab, "wmi command %d timeout\\n", cmd_id);\n\t}')
        replace('#include "CreditTrace.h"', '#include "CreditTrace.h"\n#include "SrngTrace.h"')
    restored = text
    for before, after in reversed(changes):
        if restored.count(after) != 1:
            raise ValueError("SRNG insertion is not uniquely reversible")
        restored = restored.replace(after, before, 1)
    if restored != original:
        raise ValueError("SRNG insertion changed existing protocol")
    return text.encode()

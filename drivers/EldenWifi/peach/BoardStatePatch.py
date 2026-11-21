"""Observe physical WCN state before, at and after the first PMF failure."""
import hashlib

EXPECTED = {'core.c': 'dae2ee38ca9e88e344a3755788f987b8c50232e3940713adbfe0d8545eaa7659', 'wmi.c': '38f58c57197644dc9fd5c9c4b806df6c6c1c76baf1ed932bdcdf598f8cbdd058'}


def patch(name, data):
    if hashlib.sha256(data).hexdigest() != EXPECTED.get(name):
        raise ValueError("Exact board-state runtime parent changed: " + name)
    original = text = data.decode()
    changes = []

    def replace(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise ValueError("Board-state anchor changed: " + old[:80])
        text = text.replace(old, new, 1)
        changes.append((old, new))

    marker = '#include "Ce3Timeline.inc"' if name == "core.c" else '#include "Ce3Timeline.h"'
    replace(marker, marker + '\nextern int elden_wifi_board_state(unsigned);')
    if name == "core.c":
        marker = "\t\telden_ce3_timeline(ab,12, ret);"
        replace(marker, marker + '\n\t\tif(ab->hw_rev==ATH12K_HW_PEACH_HW20)(void)elden_wifi_board_state(12);')
    else:
        marker = '\tif (param_id == WMI_PDEV_PARAM_PMF_QOS) elden_ce3_timeline(ar->ab,9,0);'
        replace(marker, marker + '''
    static unsigned board_first_pmf;
    if (ar->ab->hw_rev==ATH12K_HW_PEACH_HW20 && param_id==WMI_PDEV_PARAM_PMF_QOS &&
        !__atomic_exchange_n(&board_first_pmf,1u,__ATOMIC_ACQ_REL))
        (void)elden_wifi_board_state(9);''')
        marker = '\t\telden_ce3_inspect(wmi_ab->ab,cmd_id);'
        replace(marker, marker + '''
        static unsigned board_first_failure;
        if(wmi_ab->ab->hw_rev==ATH12K_HW_PEACH_HW20 &&
            !__atomic_exchange_n(&board_first_failure,1u,__ATOMIC_ACQ_REL))
            (void)elden_wifi_board_state(90);''')
    restored = text
    for old, new in reversed(changes):
        if restored.count(new) != 1:
            raise ValueError("Board-state observation is not reversible")
        restored = restored.replace(new, old, 1)
    if restored != original:
        raise ValueError("Board-state changed original operations")
    return text.encode()

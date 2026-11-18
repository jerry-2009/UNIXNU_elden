"""Append control metadata to the exact CE and v188 WMI production inputs."""
import hashlib

EXPECTED = {
    "ce.c": "2cc8f806c4155222635426b18d95df1cb5fd6387b35071255004ca198bccbbc1",
    "wmi.c": "c9d2eed747b9e2621f359d66f76897112599d7656cea86f4a70366e46bebfc89",
}


def patch(name, data):
    if name not in EXPECTED or hashlib.sha256(data).hexdigest() != EXPECTED[name]:
        raise ValueError("CE3 flow input differs: " + name)
    original = text = data.decode()
    changes = []

    def replace(before, after):
        nonlocal text
        if text.count(before) != 1:
            raise ValueError("CE3 flow anchor differs: " + before[:80])
        text = text.replace(before, after, 1)
        changes.append((before, after))

    if name == "ce.c":
        replace('#include "hif.h"', '#include "hif.h"\n#include "Ce3FlowTrace.inc"')
        before = '''\tif (!desc) {
\t\tskb = ERR_PTR(-EIO);
\t\tgoto err_unlock;
\t}'''
        replace(before, '''\tif (!desc) {
        if (pipe->pipe_num == 3)
            elden_wifi_ce3_flow_note(ab, EcfCeEmpty, sw_index,
                srng->u.src_ring.hp, srng->u.src_ring.cached_tp,
                srng->u.src_ring.reap_hp, 0);
\t\tskb = ERR_PTR(-EIO);
\t\tgoto err_unlock;
\t}''')
        before = '\tpipe->src_ring->skb[sw_index] = NULL;'
        replace(before, '''    if (pipe->pipe_num == 3)
        elden_wifi_ce3_flow_note(ab, EcfCeReap, sw_index,
            srng->u.src_ring.hp, srng->u.src_ring.cached_tp,
            skb ? skb->len : 0, skb ? ATH12K_SKB_CB(skb)->paddr : 0);
''' + before)
        before = '\tath12k_hal_srng_access_end(ab, srng);\n\nunlock:'
        replace(before, '''\tath12k_hal_srng_access_end(ab, srng);
    if (pipe_id == 3)
        elden_wifi_ce3_flow_note(ab, EcfCePost, write_index,
            srng->u.src_ring.hp, srng->u.src_ring.cached_tp,
            skb->len, ATH12K_SKB_CB(skb)->paddr);

unlock:
    if (pipe_id == 3 && ret)
        elden_wifi_ce3_flow_note(ab, EcfCeReject, (u32)ret, skb->len, 0, 0, 0);''')
    else:
        replace('#include "SrngTrace.h"', '#include "SrngTrace.h"\n#include "Ce3FlowTrace.h"')
        before = '\tect_set(EctWmiCmd,cmd_id);ect_add(EctWmiCalls,1);'
        replace(before, before + '''
    elden_wifi_ce3_flow_note(wmi_ab->ab, EcfWmiRequest, cmd_id, skb->len, 0, 0, 0);''')
        before = '\tect_set(EctWmiResult,(uint64_t)(int64_t)ret);if(!ret)ect_add(EctWmiOk,1);'
        replace(before, before + '''
    /* A successful CE callback may already have freed skb. Only stable scalars. */
    elden_wifi_ce3_flow_note(wmi_ab->ab, EcfWmiResult, cmd_id, (u32)ret, 0, 0, 0);''')
        before = '\t\telden_wifi_srng_first_wmi(wmi_ab->ab);'
        replace(before, '\t\telden_wifi_ce3_flow_dump(wmi_ab->ab);\n' + before)
        before = '\tret = ath12k_wmi_cmd_send(wmi, skb, WMI_PDEV_SET_PARAM_CMDID);'
        replace(before, '''    /* Parameter number/device number only; no parameter value or payload. */
    elden_wifi_ce3_flow_note(ar->ab, EcfPdevSelector, param_id, pdev_id,
        WMI_PDEV_SET_PARAM_CMDID, 0, 0);
''' + before)
    restored = text
    for before, after in reversed(changes):
        if restored.count(after) != 1:
            raise ValueError("CE3 flow insertion is not uniquely reversible")
        restored = restored.replace(after, before, 1)
    if restored != original:
        raise ValueError("CE3 flow changed an existing operation")
    return text.encode()

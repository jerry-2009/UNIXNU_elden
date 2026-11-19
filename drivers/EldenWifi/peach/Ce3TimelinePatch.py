"""Locate the first real CE3 register reset across the existing start sequence."""
import hashlib
EXPECTED={
 'core.c':'d3db43d17a45c92cb0e8f61e56e65f9caa6cb72e785b3fee55a6973bd1481f31',
 'wmi.c':'b5055cd5d865f724eb48228a2e9426162cd60d222fdde2b3c52e83b30a1e5e7f'}


def patch(name,data):
    if hashlib.sha256(data).hexdigest()!=EXPECTED[name]:raise ValueError('Exact timeline parent changed: '+name)
    old=text=data.decode();changes=[]
    def add(anchor,extra):
        nonlocal text
        if text.count(anchor)!=1:raise ValueError('Timeline anchor changed: '+anchor[:90])
        new=anchor+extra;text=text.replace(anchor,new,1);changes.append((anchor,new))
    if name=='core.c':
        add('#include "hif.h"','\n#include "Ce3Timeline.inc"')
        for stage,anchor in [(1,'\tret = ath12k_ce_init_pipes(ab);'),
                (2,'\tret = ath12k_dp_cmn_device_init(ath12k_ab_to_dp(ab));'),
                (3,'\tret = ath12k_hif_start(ab);'),
                (4,'\tret = ath12k_wmi_wait_for_service_ready(ab);'),
                (5,'\tath12k_hal_cc_config(ab);'),
                (6,'\tret = ath12k_wmi_wait_for_unified_ready(ab);'),
                (7,'\t\tret = ath12k_wmi_set_hw_mode(ab, WMI_HOST_HW_MODE_DBS);'),
                (8,'\tret = ath12k_dp_tx_htt_h2t_ver_req_msg(ab);')]:
            add(anchor,'\n'+('\t\t' if stage==7 else '\t')+'elden_ce3_timeline(ab,'+str(stage)+', '+('0' if stage==5 else 'ret')+');')
    else:
        add('#include "Ce3Inspect.inc"','\n#include "Ce3Timeline.h"')
        marker='\tret = ath12k_wmi_cmd_send(wmi, skb, WMI_PDEV_SET_PARAM_CMDID);'
        if text.count(marker)!=1:raise ValueError('PDEV send boundary changed')
        extra='\tif (param_id == WMI_PDEV_PARAM_PMF_QOS) elden_ce3_timeline(ar->ab,9,0);\n'
        text=text.replace(marker,extra+marker,1);changes.append((marker,extra+marker))
    restored=text
    for anchor,new in reversed(changes):
        if restored.count(new)!=1:raise ValueError('Timeline insertion not reversible')
        restored=restored.replace(new,anchor,1)
    if restored!=old:raise ValueError('Timeline changed original operations')
    return text.encode()

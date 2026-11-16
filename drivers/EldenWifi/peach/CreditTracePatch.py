"""Reversible scalar observations around original HTC/CE/WMI operations."""
import hashlib
EXPECTED={
 'htc.c':'a3a445e4d5cebd2cb012390cae534b434d86681ba02cd987b7581bd670ff8395',
 'pci.c':'73d73c5b4dc7be0ce3d76dc46315addd74438810a676c743147385dad2c4e8be',
 'wmi.c':'aaa6b296361c48b7407150cc79ec825bf4943f02038b022370d35975c411ca31'}
def patch(name,data):
    if hashlib.sha256(data).hexdigest()!=EXPECTED[name]:raise ValueError('Credit trace source differs: '+name)
    original=data.decode();text=original;changes=[]
    def change(old,new):
        nonlocal text
        if text.count(old)!=1:raise ValueError('Credit trace anchor differs: '+old[:80])
        text=text.replace(old,new,1);changes.append((old,new))
    if name=='htc.c':
        old='\tskb_push(skb, sizeof(struct ath12k_htc_hdr));'
        change(old,'''    ect_add(ect_ep(eid,EctTxAttempt),1);
    ect_set(ect_ep(eid,EctFlow),ep->tx_credit_flow_enabled);ect_set(ect_ep(eid,EctCreditSize),htc->target_credit_size);
    ect_set(ect_ep(eid,EctService),ep->service_id);ect_set(ect_ep(eid,EctUlPipe),ep->ul_pipe_id);ect_set(ect_ep(eid,EctDlPipe),ep->dl_pipe_id);
'''+old)
        old='\t\tif (ep->tx_credits < credits) {'
        change(old,old+'\n\t\t\tect_add(ect_ep(eid,EctNoCredit),1);\n\t\t\tect_set(ect_ep(eid,EctCurrent),(uint64_t)(int64_t)ep->tx_credits);')
        old='\t\tep->tx_credits -= credits;'
        change(old,old+'\n\t\tect_set(ect_ep(eid,EctCurrent),(uint64_t)(int64_t)ep->tx_credits);')
        old='\tath12k_htc_prepare_tx_skb(ep, skb);'
        change(old,old+'''
    ect_set(ect_ep(eid,EctTxInfo),le32_to_cpu(((struct ath12k_htc_hdr *)skb->data)->htc_info));
    ect_set(ect_ep(eid,EctTxCtrl),le32_to_cpu(((struct ath12k_htc_hdr *)skb->data)->ctrl_info));''')
        old='\tret = ath12k_ce_send(htc->ab, skb, ep->ul_pipe_id, ep->eid);'
        change(old,old+'\n\tect_add(ect_ep(eid,ret?EctTxFail:EctTxOk),1);')
        old='\t\tep->tx_credits += report->credits;'
        change(old,old+'''
        ect_add(ect_ep(report->eid,EctReport),1);ect_add(ect_ep(report->eid,EctAdded),report->credits);
        ect_set(ect_ep(report->eid,EctCurrent),(uint64_t)(int64_t)ep->tx_credits);
        ect_set(ect_ep(report->eid,EctCallback),ep->ep_ops.ep_tx_credits!=0);''')
        old='\tpayload_len = le32_get_bits(hdr->htc_info, HTC_HDR_PAYLOADLEN);'
        change(old,'''    ect_add(ect_ep(eid,EctRx),1);
    ect_set(ect_ep(eid,EctRxInfo),le32_to_cpu(hdr->htc_info));ect_set(ect_ep(eid,EctRxCtrl),le32_to_cpu(hdr->ctrl_info));
'''+old)
        old='\tif (trailer_present) {'
        change(old,old+'\n\t\tect_add(ect_ep(eid,EctTrailer),1);')
        old='\tep->tx_credits = tx_alloc;'
        change(old,old+'\n\tect_set(ect_ep(assigned_eid,EctAlloc),tx_alloc);\n\tect_set(ect_ep(assigned_eid,EctCurrent),tx_alloc);')
        start=text.index('int ath12k_htc_connect_service(');end=text.index('\nint ath12k_htc_start(',start)
        old=text[start:end];tail='\treturn status;\n}'
        assert old.count(tail)==1
        new=old.replace(tail,'''    ect_set(ect_ep(assigned_eid,EctFlow),ep->tx_credit_flow_enabled);
    ect_set(ect_ep(assigned_eid,EctCreditSize),htc->target_credit_size);
    ect_set(ect_ep(assigned_eid,EctUlPipe),ep->ul_pipe_id);ect_set(ect_ep(assigned_eid,EctDlPipe),ep->dl_pipe_id);
    ect_set(ect_ep(assigned_eid,EctService),ep->service_id);
'''+tail)
        change(old,new)
    elif name=='pci.c':
        old='\tath12k_ce_per_engine_service(ce_pipe->ab, ce_pipe->pipe_num);'
        change(old,'\tect_add(ect_ce(ce_pipe->pipe_num,EctCeEnter),1);\n'+old+'\n\tect_add(ect_ce(ce_pipe->pipe_num,EctCeExit),1);')
        old='\tif (!test_bit(ATH12K_FLAG_CE_IRQ_ENABLED, &ab->dev_flags))\n\t\treturn IRQ_HANDLED;'
        change(old,'''    ect_add(ect_ce(ce_pipe->pipe_num,EctCeIrq),1);
    ect_set(EctDevFlags,ab->dev_flags);
    if (!test_bit(ATH12K_FLAG_CE_IRQ_ENABLED, &ab->dev_flags))ect_add(ect_ce(ce_pipe->pipe_num,EctCeOff),1);
'''+old)
    elif name=='wmi.c':
        old='\twait_event_timeout_once(wmi_ab->tx_credits_wq, ({'
        change(old,'\tect_set(EctWmiCmd,cmd_id);ect_add(EctWmiCalls,1);\n'+old)
        old='\tif (ret == -EAGAIN)\n\t\tath12k_warn(wmi_ab->ab, "wmi command %d timeout\\n", cmd_id);'
        change(old,'\tect_set(EctWmiResult,(uint64_t)(int64_t)ret);if(!ret)ect_add(EctWmiOk,1);\n'+old)
    recovered=text
    for old,new in reversed(changes):
        assert recovered.count(new)==1
        recovered=recovered.replace(new,old,1)
    assert recovered==original
    prefix='#include "CreditTrace.h"\n'
    if name=='htc.c':prefix+='volatile uint64_t elden_wifi_credit_trace[EctWords]={0};\n'
    return (prefix+text).encode()

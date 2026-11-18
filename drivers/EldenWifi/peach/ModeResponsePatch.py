"""Preserve v190 operations while observing qualified response/R0 fields."""
import hashlib
EXPECTED="ceeead747c7812bfde3088b22fe28e7339a4b8e09ab8c88d5559bfac6aa24976"
def patch(data):
    if hashlib.sha256(data).hexdigest()!=EXPECTED:raise ValueError('Response trace input differs')
    original=text=data.decode();changes=[]
    def replace(before,after):
        nonlocal text
        if text.count(before)!=1:raise ValueError('Response anchor differs')
        text=text.replace(before,after,1);changes.append((before,after))
    replace('int ath12k_wmi_cmd_send(', '#include "ModeResponseTrace.inc"\n\nint ath12k_wmi_cmd_send(')
    before='\tid = le32_get_bits(cmd_hdr->cmd_id, WMI_CMD_HDR_CMD_ID);'
    replace(before,before+'\n\temr_event(ab,skb,id);')
    before='\t\telden_wifi_ce3_flow_dump(wmi_ab->ab);'
    replace(before,'\t\temr_ring(wmi_ab->ab);\n'+before)
    restored=text
    for before,after in reversed(changes):
        if restored.count(after)!=1:raise ValueError('Response insertion is not uniquely reversible')
        restored=restored.replace(after,before,1)
    if restored!=original:raise ValueError('Response insertion changed existing operations')
    return text.encode()

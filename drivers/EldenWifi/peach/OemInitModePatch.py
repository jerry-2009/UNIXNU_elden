"""Match Peach startup to OEM preferred-mode initialization, preserving alias0."""
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EXPECTED={'core.c':'7c25574bd98e89313b62c6abe2a0ef1b059455beaea7d0013b9b66065578d531',
          'wmi.c':'14794e784a472315a57640d4b21c1ae2b53019f3d08ebb4199aa42deb4f2611a'}


def patch(name,data):
    if hashlib.sha256(data).hexdigest()!=EXPECTED.get(name):raise ValueError('Exact OEM-init parent changed: '+name)
    original=text=data.decode();changes=[]
    def replace(old,new):
        nonlocal text
        if text.count(old)!=1:raise ValueError('OEM-init anchor changed: '+old[:90])
        text=text.replace(old,new,1);changes.append((old,new))
    if name=='core.c':
        old='\t/* put hardware to DBS mode */\n\tif (ab->hw_params->single_pdev_only) {'
        new='\t/* Peach mode was supplied in WMI_INIT using firmware capabilities. */\n\tif (ab->hw_params->single_pdev_only && ab->hw_rev != ATH12K_HW_PEACH_HW20) {'
        replace(old,new)
    else:
        replace('int ath12k_wmi_cmd_init(struct ath12k_base *ab)',(ROOT/'OemInitMode.inc').read_text(encoding='utf-8')+'\nint ath12k_wmi_cmd_init(struct ath12k_base *ab)')
        marker='\tath12k_fill_band_to_mac_param(ab, arg.band_to_mac);'
        replace(marker,marker+'\n\tint init_mode=elden_wifi_oem_init_mode(ab,&arg);\n\tif(init_mode)return init_mode;')
    restored=text
    for old,new in reversed(changes):
        if restored.count(new)!=1:raise ValueError('OEM-init delta not reversible')
        restored=restored.replace(new,old,1)
    if restored!=original:raise ValueError('Other original operations changed')
    return text.encode()

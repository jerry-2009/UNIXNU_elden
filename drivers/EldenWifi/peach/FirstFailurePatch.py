"""Observe ready and first actual UMAC failure on the exact qualified runtime."""
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EXPECTED={'pci.c':'8bf572fb51ca83bcacbaa20ee8e0ef562ab6888e226c975c51cc38a11e522bba',
          'core.c':'c6a33ec57fc499f773e8aa8c74a963f566a75762553cb8c239c3163cac5ba538'}


def patch(name,data):
    if hashlib.sha256(data).hexdigest()!=EXPECTED.get(name):raise ValueError('Exact first-failure parent changed: '+name)
    original=text=data.decode();changes=[]
    def replace(old,new):
        nonlocal text
        if text.count(old)!=1:raise ValueError('First-failure anchor changed: '+old[:80])
        text=text.replace(old,new,1);changes.append((old,new))
    if name=='pci.c':
        marker='static int elden_umac_wake_get(struct ath12k_base *ab)'
        replace(marker,'void elden_wifi_first_failure_sample(struct ath12k_base *,u32,int);\n'+marker)
        marker='    if (ret) mhi_device_put(elden_umac_device);'
        replace(marker,'    if (ret) {elden_wifi_first_failure_sample(ab,90,ret);mhi_device_put(elden_umac_device);}')
        marker='int ath12k_pci_hif_suspend(struct ath12k_base *ab)'
        replace(marker,(ROOT/'FirstFailurePci.inc').read_text(encoding='utf-8')+'\n'+marker)
    else:
        marker='extern int elden_wifi_board_state(unsigned);'
        replace(marker,marker+'\nextern void elden_wifi_first_failure_sample(struct ath12k_base *,u32,int);')
        marker='\t\tif(ab->hw_rev==ATH12K_HW_PEACH_HW20)(void)elden_wifi_board_state(12);'
        replace(marker,marker+'\n\t\tif(ab->hw_rev==ATH12K_HW_PEACH_HW20)elden_wifi_first_failure_sample(ab,12,ret);')
    restored=text
    for old,new in reversed(changes):
        if restored.count(new)!=1:raise ValueError('First-failure observation not uniquely reversible')
        restored=restored.replace(new,old,1)
    if restored!=original:raise ValueError('First-failure changed original operations')
    return text.encode()

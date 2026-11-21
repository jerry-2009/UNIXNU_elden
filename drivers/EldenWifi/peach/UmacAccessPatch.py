"""One bounded OEM access-handshake contrast on the first real PMF command."""
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EXPECTED={'pci.c':'d50605c5a03a0c5b2b8b949a2ebc02c3329cd7e683746f47d8765eeb38acb84c',
          'wmi.c':'14794e784a472315a57640d4b21c1ae2b53019f3d08ebb4199aa42deb4f2611a'}


def patch(name,data):
    if hashlib.sha256(data).hexdigest()!=EXPECTED.get(name):raise ValueError('Exact first-access parent changed: '+name)
    text=original=data.decode()
    if name=='pci.c':
        marker='int ath12k_pci_hif_suspend(struct ath12k_base *ab)'
        new=(ROOT/'UmacAccess.inc').read_text(encoding='utf-8')+'\n'+marker
    else:
        marker='\tif (param_id == WMI_PDEV_PARAM_PMF_QOS) elden_ce3_timeline(ar->ab,9,0);'
        new='''\tif (param_id == WMI_PDEV_PARAM_PMF_QOS) {
\t\textern int elden_wifi_umac_access_first(struct ath12k_base *);
\t\tret=elden_wifi_umac_access_first(ar->ab);
\t\telden_ce3_timeline(ar->ab,9,ret);
\t\tif(ret){dev_kfree_skb(skb);return ret;}
\t}'''
    if text.count(marker)!=1:raise ValueError('First-access anchor changed')
    text=text.replace(marker,new,1)
    if text.replace(new,marker,1)!=original:raise ValueError('Unexpected first-access delta')
    return text.encode()

"""Use an actual MHI wake lease for one optional Peach power-state trial."""
import hashlib
from pathlib import Path

EXPECTED='73d73c5b4dc7be0ce3d76dc46315addd74438810a676c743147385dad2c4e8be'
ROOT=Path(__file__).resolve().parents[1]


def patch(data):
    if hashlib.sha256(data).hexdigest()!=EXPECTED:raise ValueError('Plain PCI runtime identity changed')
    original=text=data.decode();changes=[]
    def replace(old,new):
        nonlocal text
        if text.count(old)!=1:raise ValueError('MHI wake lease anchor changed: '+old[:90])
        text=text.replace(old,new,1);changes.append((old,new))
    replace('int ath12k_pci_hif_suspend(struct ath12k_base *ab)',
            (ROOT/'MhiLease.inc').read_text(encoding='utf-8')+'\nint ath12k_pci_hif_suspend(struct ath12k_base *ab)')
    start=text.index('int ath12k_pci_start(struct ath12k_base *ab)');end=text.index('\n}\n',start)+3
    old=text[start:end];new=old.replace('struct ath12k_pci *ab_pci = ath12k_pci_priv(ab);',
        'struct ath12k_pci *ab_pci = ath12k_pci_priv(ab);\n\tint lease = elden_mhi_lease_get(ab);\n\tif (lease) return lease;',1)
    replace(old,new)
    for name in ('ath12k_pci_stop','ath12k_pci_power_down'):
        start=text.index('void '+name+'(');end=text.index('\n}\n',start)+3
        old=text[start:end];anchor='struct ath12k_pci *ab_pci = ath12k_pci_priv(ab);'
        if old.count(anchor)!=1:raise ValueError('MHI lease release anchor changed')
        replace(old,old.replace(anchor,anchor+'\n\telden_mhi_lease_put(ab);',1))
    restored=text
    for old,new in reversed(changes):
        if restored.count(new)!=1:raise ValueError('MHI lease is not uniquely reversible')
        restored=restored.replace(new,old,1)
    if restored!=original:raise ValueError('Other PCI statements changed')
    return text.encode()

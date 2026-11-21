"""Observe only the exact original-shadow/window-reselect PCI lifecycle."""
import hashlib
from pathlib import Path

EXPECTED='f56c5ee0fd553d64d34938426c3ac84623c5bf39774648a8b2f016f7279fac0f'
ROOT=Path(__file__).resolve().parents[1]


def patch(data):
    if hashlib.sha256(data).hexdigest()!=EXPECTED:
        raise ValueError('Exact window-reselect PCI parent changed')
    original=text=data.decode();changes=[]
    def replace(old,new):
        nonlocal text
        if text.count(old)!=1:raise ValueError('PCI state boundary changed: '+old[:80])
        text=text.replace(old,new,1);changes.append((old,new))
    replace('int ath12k_pci_hif_suspend(struct ath12k_base *ab)',
        (ROOT/'PciStateTrace.inc').read_text(encoding='utf-8')+'\nint ath12k_pci_hif_suspend(struct ath12k_base *ab)')
    replace('\tif (wake) return wake;', '\tif (wake) return wake;\n\telden_pci_state_install(ab);')
    # Capture the original put write before restoring the formerly-null hook.
    old='\tath12k_ce_cleanup_pipes(ab);\n\telden_umac_wake_put(ab);'
    replace(old,old+'\n\telden_pci_state_remove(ab);')
    old='\tstruct ath12k_pci *ab_pci = ath12k_pci_priv(ab);\n\telden_umac_wake_put(ab);'
    replace(old,old+'\n\telden_pci_state_remove(ab);')
    start=text.index('u32 ath12k_pci_read32(');end=text.index('\nEXPORT_SYMBOL(ath12k_pci_read32);',start)
    old=text[start:end]
    new=old.replace('\tu32 val, window_start;', '\tu32 val, window_start;\n\tu32 state_requested=offset;',1)
    if new.count('\treturn val;')!=1:raise ValueError('PCI read return changed')
    new=new.replace('\treturn val;', '\telden_pci_state_read(ab,state_requested,val);\n\treturn val;',1)
    replace(old,new)
    restored=text
    for old,new in reversed(changes):
        if restored.count(new)!=1:raise ValueError('PCI state observation not reversible')
        restored=restored.replace(new,old,1)
    if restored!=original:raise ValueError('PCI original operations changed')
    return text.encode()

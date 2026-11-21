"""Use Peach OEM's no-local-cache window selection, preserving its exact write.

default_config.h defines PCIE_REG_WINDOW_LOCAL_NO_CACHE1. Hardware timeline
observed window0 while the cached CE3 selection stayed37. The selection value,
lock, accessor and existing readback remain unchanged; no guessed barrier.
"""
import hashlib
EXPECTED='7c80e0f3be2b3a059e3d4b36459b915fdd037257ecd0ac650b32460a687f2608'


def function(text):
    start=text.index('static void ath12k_pci_select_window(')
    return text[start:text.index('\n}\n',start)+3]


def patch(data):
    if hashlib.sha256(data).hexdigest()!=EXPECTED:raise ValueError('Exact OEM UMAC PCI parent changed')
    text=data.decode();old=function(text)
    marker='\tif (window != ab_pci->register_window) {'
    replacement='\tif (ab->hw_rev == ATH12K_HW_PEACH_HW20 || window != ab_pci->register_window) {'
    if old.count(marker)!=1:raise ValueError('Original window-select condition changed')
    new=old.replace(marker,replacement,1)
    if new.replace(replacement,marker,1)!=old:raise ValueError('Unexpected window delta')
    return text.replace(old,new,1).encode()

"""Propagate MSI config failures in the exact frozen Ath12k board adapter."""
import hashlib
from pathlib import Path
EXPECTED='db549a0909d25e102e9ccc8025504f61900271cd290e1db2f23a704447669c94'
def patch(data):
    if hashlib.sha256(data).hexdigest()!=EXPECTED:raise ValueError('Frozen nw_pci.c differs')
    text=data.decode();start=text.index('int pci_alloc_irq_vectors(');end=text.index('int pci_irq_vector(',start)
    replacement=(Path(__file__).with_name('PciMsi.inc')).read_text(encoding='utf-8')
    return (text[:start]+replacement+'\n'+text[end:]).encode()

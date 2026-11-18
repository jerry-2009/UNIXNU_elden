"""Trace the actual PCI read branch without changing original access statements."""
import hashlib
import re

EXPECTED = "a66509b76455d2b64ce29eaf2dd0c2a335af4c7fa8c795a77f3447c76119594d"


def patch(data):
    if hashlib.sha256(data).hexdigest() != EXPECTED:
        raise ValueError("PCI trace input differs")
    text = original = data.decode()
    changes = []

    def replace(before, after):
        nonlocal text
        if text.count(before) != 1:
            raise ValueError("PCI trace anchor differs")
        text = text.replace(before, after, 1)
        changes.append((before, after))

    start = text.index('u32 ath12k_pci_read32(')
    end = text.index('\nEXPORT_SYMBOL(ath12k_pci_read32);', start)
    old = text[start:end]
    new = old.replace('\tint ret = 0;', '\tint ret = 0;\n\tu32 epw_request = offset, epw_effective = 0xffffffffU, epw_window = 0;', 1)
    new = new.replace('\t\tval = ioread32(ab->mem + offset);', '\t\tepw_effective = offset;\n\t\tval = ioread32(ab->mem + offset);', 1)
    new = new.replace('\t\tif (window_start == WINDOW_START) {', '\t\tepw_window = window_start;\n\t\tif (window_start == WINDOW_START) {', 1)
    new = new.replace('\t\t\t\tval = ioread32(ab->mem +\n\t\t\t\t\t       (offset & WINDOW_RANGE_MASK));', '\t\t\t\tepw_effective = offset & WINDOW_RANGE_MASK;\n\t\t\t\tval = ioread32(ab->mem +\n\t\t\t\t\t       (offset & WINDOW_RANGE_MASK));', 1)
    for indent in ('\t\t\t\t','\t\t\t'):
        line=indent+'val = ioread32(ab->mem + window_start +'
        new,n=re.subn('^'+re.escape(line),lambda m:indent+'epw_effective = window_start + (offset & WINDOW_RANGE_MASK);\n'+line,new,count=1,flags=re.M)
        if n!=1:raise ValueError('PCI effective read branch differs')
    marker='\n\tif (test_bit(ATH12K_PCI_FLAG_INIT_DONE, &ab_pci->flags) &&\n\t    offset >= ACCESS_ALWAYS_OFF && ab_pci->pci_ops->release'
    if new.count(marker) != 1:
        raise ValueError("PCI release boundary differs")
    new = new.replace(marker, '\n\tepw_note(ab, epw_request, epw_effective, epw_window, ret, val);\n' + marker, 1)
    replace(old, new)
    replace('u32 ath12k_pci_read32(', '#include "PciWindowTrace.inc"\n\nu32 ath12k_pci_read32(')
    restored = text
    for before, after in reversed(changes):
        if restored.count(after) != 1:
            raise ValueError("PCI trace is not uniquely reversible")
        restored = restored.replace(after, before, 1)
    if restored != original:
        raise ValueError("PCI trace changed original statements")
    return text.encode()

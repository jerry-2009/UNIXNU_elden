"""Replace the whole-start UMAC hold with the original HAL access scope."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = 'ad5d2a2bb68a68b3f047abd5d0cc9abf38c7c06c83ca40fa56c1408fe99ae082'
VENDOR = 'd50b305f7da9e14715a25120a4ac7b1a4b8b97c3'


def body(text, marker):
    start = text.index(marker)
    end = text.index('\n}\n', start) + 3
    return text[start:end]


def patch(data):
    if hashlib.sha256(data).hexdigest() != EXPECTED:
        raise ValueError('Exact posted-reset PCI input changed')
    original = text = data.decode()
    changes = []

    def replace(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise ValueError('UMAC register anchor changed: ' + old[:80])
        text = text.replace(old, new, 1)
        changes.append((old, new))

    old = (ROOT / 'UmacWake.inc').read_text(encoding='utf-8')
    prototypes = ('static u32 elden_pci_read32_raw(struct ath12k_base *, u32);\n'
                  'static void elden_pci_write32_raw(struct ath12k_base *, u32, u32);\n')
    replace(old, prototypes + (ROOT / 'UmacRegisterAccess.inc').read_text(encoding='utf-8'))
    wake = '''\tif (test_bit(ATH12K_PCI_FLAG_INIT_DONE, &ab_pci->flags) &&
\t    offset >= ACCESS_ALWAYS_OFF && ab_pci->pci_ops->wakeup)
\t\tret = ab_pci->pci_ops->wakeup(ab);'''
    release = '''\tif (test_bit(ATH12K_PCI_FLAG_INIT_DONE, &ab_pci->flags) &&
\t    offset >= ACCESS_ALWAYS_OFF && ab_pci->pci_ops->release &&
\t    !ret)
\t\tab_pci->pci_ops->release(ab);'''
    for marker, rawname in [('u32 ath12k_pci_read32(', 'elden_pci_read32_raw'),
                            ('void ath12k_pci_write32(', 'elden_pci_write32_raw')]:
        old = body(text, marker)
        name = 'ath12k_pci_read32' if 'read32' in marker else 'ath12k_pci_write32'
        if old.count(wake) != 1 or old.count(release) != 1:
            raise ValueError('Original per-register MHI scope changed')
        raw = 'static ' + old.replace(name, rawname, 1)
        raw = raw.replace('\tint ret = 0;\n', '', 1).replace(wake, '', 1).replace(release, '', 1)
        isread = 'read32' in marker
        wrapper = '''
@TYPE@ @NAME@(struct ath12k_base *ab, u32 offset@VALUE@)
{
    struct ath12k_pci *pci = ath12k_pci_priv(ab);
    bool taken = false;
    int ret = 0;
    if (elden_umac_access_enabled && ab->hw_rev == ATH12K_HW_PEACH_HW20) {
        ret = elden_umac_register_begin(ab, offset, &taken);
        if (ret) @REFUSE@;
        @CALL@
        elden_umac_register_end(ab, taken);
        @RETURN@
    }
    /* Preserve the inherited non-Peach and pre-binding MHI behavior. */
    if (test_bit(ATH12K_PCI_FLAG_INIT_DONE, &pci->flags) &&
        offset >= ACCESS_ALWAYS_OFF && pci->pci_ops->wakeup)
        ret = pci->pci_ops->wakeup(ab);
    @CALL@
    if (test_bit(ATH12K_PCI_FLAG_INIT_DONE, &pci->flags) &&
        offset >= ACCESS_ALWAYS_OFF && pci->pci_ops->release && !ret)
        pci->pci_ops->release(ab);
    @RETURN@
}
'''.replace('@TYPE@', 'u32' if isread else 'void').replace('@NAME@', name).replace('@VALUE@', '' if isread else ', u32 value')
        wrapper = wrapper.replace('@REFUSE@', 'return 0xffffffffU' if isread else 'return')
        wrapper = wrapper.replace('@CALL@', 'u32 val = elden_pci_read32_raw(ab, offset);' if isread else 'elden_pci_write32_raw(ab, offset, value);')
        wrapper = wrapper.replace('@RETURN@', 'return val;' if isread else 'return;')
        replace(old, raw + wrapper)
    restored = text
    for old, new in reversed(changes):
        if restored.count(new) != 1:
            raise ValueError('UMAC register changes not uniquely reversible')
        restored = restored.replace(new, old, 1)
    if restored != original:
        raise ValueError('Unrelated PCI statements changed')
    return text.encode()

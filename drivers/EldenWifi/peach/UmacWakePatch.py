"""Explicit OEM Peach MHI+UMAC wake trial over the plain PCI runtime."""
import hashlib
from pathlib import Path

EXPECTED = '73d73c5b4dc7be0ce3d76dc46315addd74438810a676c743147385dad2c4e8be'
ROOT = Path(__file__).resolve().parents[1]


def patch(data):
    if hashlib.sha256(data).hexdigest() != EXPECTED:
        raise ValueError('Plain PCI runtime identity changed')
    original = text = data.decode()
    changes = []

    def replace(before, after):
        nonlocal text
        if text.count(before) != 1:
            raise ValueError('UMAC wake anchor changed: ' + before[:90])
        text = text.replace(before, after, 1)
        changes.append((before, after))

    marker = 'int ath12k_pci_hif_suspend(struct ath12k_base *ab)'
    replace(marker, (ROOT / 'UmacWake.inc').read_text(encoding='utf-8') + '\n' + marker)
    start = text.index('int ath12k_pci_start(struct ath12k_base *ab)')
    end = text.index('\n}\n', start) + 3
    before = text[start:end]
    marker = '\tset_bit(ATH12K_PCI_FLAG_INIT_DONE, &ab_pci->flags);'
    if before.count(marker) != 1:
        raise ValueError('Original start admission changed')
    replace(before, before.replace(marker, marker +
        '\n\tint wake = elden_umac_wake_get(ab);\n\tif (wake) return wake;', 1))
    start = text.index('void ath12k_pci_stop(struct ath12k_base *ab)')
    end = text.index('\n}\n', start) + 3
    before = text[start:end]
    marker = '\tath12k_ce_cleanup_pipes(ab);'
    if before.count(marker) != 1:
        raise ValueError('Original CE cleanup changed')
    replace(before, before.replace(marker, marker + '\n\telden_umac_wake_put(ab);', 1))
    start = text.index('void ath12k_pci_power_down(struct ath12k_base *ab, bool is_suspend)')
    end = text.index('\n}\n', start) + 3
    before = text[start:end]
    marker = '\tstruct ath12k_pci *ab_pci = ath12k_pci_priv(ab);'
    if before.count(marker) != 1:
        raise ValueError('Original power-down changed')
    replace(before, before.replace(marker, marker + '\n\telden_umac_wake_put(ab);', 1))
    restored = text
    for before, after in reversed(changes):
        if restored.count(after) != 1:
            raise ValueError('UMAC insertions not uniquely reversible')
        restored = restored.replace(after, before, 1)
    if restored != original:
        raise ValueError('Other PCI statements changed')
    return text.encode()

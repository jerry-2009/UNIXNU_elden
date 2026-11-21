"""Publish the actual Peach WAKE MSI as the original CNSS host-cap path does."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = '863a1bc2c6d35ce012b1ebdf374b7110cb35bf227ad79bf4bce703af484a3715'


def patch(data):
    if hashlib.sha256(data).hexdigest() != EXPECTED:
        raise ValueError('Exact prepared QMI input changed')
    text = data.decode()
    marker = 'static noinline_for_stack\nint ath12k_qmi_host_cap_send(struct ath12k_base *ab)'
    if text.count(marker) != 1:
        raise ValueError('Host capability definition changed')
    helper = '#include "hif.h"\n' + (ROOT / 'HostWakeCapability.inc').read_text(encoding='utf-8') + '\n'
    text = text.replace(marker, helper + marker, 1)
    start = text.index('int ath12k_qmi_host_cap_send(')
    end = text.index('\n}\n', start) + 3
    old = block = text[start:end]
    marker = '\treq.num_clients_valid = 1;'
    added = '\tret = elden_wifi_host_wake_capability(ab, &req);\n\tif (ret) return ret;\n'
    if block.count(marker) != 1:
        raise ValueError('Host capability initialization changed')
    block = block.replace(marker, added + marker, 1)
    text = text.replace(old, block, 1)
    if text.replace(added, '', 1).replace(helper, '', 1) != data.decode():
        raise ValueError('Host wake change is not reversible')
    return text.encode()

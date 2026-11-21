"""Flush the two global-reset writes as pinned TB322FC Linux already does."""
import hashlib

EXPECTED = "d50605c5a03a0c5b2b8b949a2ebc02c3329cd7e683746f47d8765eeb38acb84c"
UPSTREAM = "55f3aa06951cac78b0206bde961c8cf11929a27a"
READBACK = ("\t/* Flush the posted write to the device */\n"
            "\tath12k_pci_read32(ab, PCIE_SOC_GLOBAL_RESET);\n")


def reset_body(text):
    start = text.index("static void ath12k_pci_soc_global_reset(")
    end = text.index("\n}\n", start) + 3
    return text[start:end]


def patch(data):
    if hashlib.sha256(data).hexdigest() != EXPECTED:
        raise ValueError("Exact qualified PCI state source changed")
    original = data.decode()
    body = reset_body(original)
    write = "\tath12k_pci_write32(ab, PCIE_SOC_GLOBAL_RESET, val);\n"
    if body.count(write) != 2 or READBACK in body:
        raise ValueError("Global-reset write sequence changed")
    changed = body.replace(write, write + READBACK)
    text = original.replace(body, changed, 1)
    if text.replace(READBACK, "") != original:
        raise ValueError("Posted-reset patch changed original operations")
    return text.encode()

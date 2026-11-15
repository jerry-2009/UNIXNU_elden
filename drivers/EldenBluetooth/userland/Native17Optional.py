"""Port Sheng's optional HCI callback policy to the exact original21H461 image.

Only three optional callbacks change their initialization-chain result. Actual
controller replies/logging and kernel link/timeout guards remain unchanged.
"""
from Native17 import BASE
SITES={
    'host_buffer':(BASE+0x184c60,0xaa1303e0,0xaa1f03e0),
    # Preserve the zero-status fast path; rejected requests follow the original
    # unsupported-flow logging path, which then advances without host flow.
    'host_flow':(BASE+0x184c94,0x540001c1,0x340001c0),
    'erroneous_data':(BASE+0x184d4c,0xaa1303e0,0xaa1f03e0),
}
def apply(image):
    if not image.routed:raise ValueError('Native17 routing is required')
    for _,(site,old,new) in SITES.items():image.put(site,[new],[old])
    return image

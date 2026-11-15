"""Refresh standard scan flags after successful native HCI discovery."""
import struct
from Native17 import branch,cbnz
from Native17Completion import DONE
from Native17Scan import apply as scan,SET_HCI

def apply(image):
    scan(image)
    start=image.cursor
    ready=image.emit('scan_after_discovery',[
        0xa9bf7bf3,0xaa0003f3,lambda pc:cbnz(pc,0,start+16),
        lambda pc:branch(pc,SET_HCI,True),0xaa1303e0,0xa8c17bf3,
        0x7100001f,lambda pc:branch(pc,DONE+4)])
    # Redirect only the final branch of our own verified generated thunk.
    # Its table still compares against the original zero padding, not a prior patch.
    site=image.entries['native_init_result']+52;off=image.offset(site)
    before=struct.pack('<I',branch(site,DONE+4));after=struct.pack('<I',branch(site,ready))
    if image.data[off:off+4]!=before:raise ValueError('Native completion continuation differs')
    matches=[e for e in image.edits if e['offset']<=off and off+4<=e['offset']+len(bytes.fromhex(e['after']))]
    if len(matches)!=1:raise ValueError('Ambiguous generated completion region')
    e=matches[0];delta=off-e['offset'];data=bytearray.fromhex(e['after'])
    if any(bytes.fromhex(e['before'])):raise ValueError('Completion is not original padding')
    data[delta:delta+4]=after;e['after']=data.hex();image.data[off:off+4]=after
    return image

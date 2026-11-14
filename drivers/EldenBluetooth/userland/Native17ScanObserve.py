"""Publish first, then report a relocated native capability-page address."""
import struct
from Native17 import branch,cbnz,address
from Native17Completion import DONE,SUPPORT
from Native17Scan import apply as scan,SET_HCI

def replace_owned_word(image,site,old,new,original_padding=False):
    off=image.offset(site);before=struct.pack('<I',old);after=struct.pack('<I',new)
    if image.data[off:off+4]!=before:raise ValueError('Generated diagnostic word differs')
    edits=[e for e in image.edits if e['offset']<=off and off+4<=e['offset']+len(bytes.fromhex(e['after']))]
    if len(edits)!=1:raise ValueError('Ambiguous generated diagnostic edit')
    e=edits[0]
    if original_padding and any(bytes.fromhex(e['before'])):raise ValueError('Expected original padding')
    data=bytearray.fromhex(e['after']);delta=off-e['offset'];data[delta:delta+4]=after
    e['after']=data.hex();image.data[off:off+4]=after

def apply(image):
    scan(image)
    marker=image.entries['native_init_result'];start=image.cursor
    observe=image.emit('scan_before_observation',[
        0xa9bf7bf3,0xaa0003f3,lambda pc:cbnz(pc,0,start+16),
        lambda pc:branch(pc,SET_HCI,True),0xaa1303e0,0xa8c17bf3,
        lambda pc:branch(pc,marker)])
    replace_owned_word(image,DONE,branch(DONE,marker),branch(DONE,observe))
    # Marker arg3 was zero; it now names this image's relocated support page.
    # The observer uses bounded copyin only, after exact process/CDHash checks.
    replace_owned_word(image,marker+24,0x52800003,address(marker+24,3,SUPPORT)[0],True)
    return image

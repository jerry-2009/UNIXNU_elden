"""Publish real standard extended-scan support for exact 21H461 type zero.

Policy follows QcaBluetooth Type0.c: both 0x2041/0x2042 must be supported,
and Apple's vendor scanning extension remains disabled. iOS17 addresses below
are independently decoded from its original constructor, vtable and setters.
"""
import struct
from Native17 import BASE,branch,address
from Native17Completion import apply as completion,SUPPORT
GETTER=BASE+0x2d5cbc
SET_HCI=BASE+0x216ee0
SET_VENDOR=BASE+0x216f34
CACHE=BASE+0x93e8b0
LOWER=BASE+0x93c32e
VENDOR=BASE+0x93c32d

def scan(image):
    completion(image)
    for index,opcode,bits in [(0xd7,0x2041,0x2520),(0xd8,0x2042,0x2540)]:
        if struct.unpack_from('<HH',image.original,image.offset(BASE+0x925dc0+index*24)+2)!=(opcode,bits):
            raise ValueError('Extended scan descriptor differs')
    # Constructor selects this exact vtable, whose slot 0x778 is the getter.
    pointer=struct.unpack_from('<Q',image.original,image.offset(BASE+0x8db430+0x778))[0]
    if pointer>>63 or BASE+(pointer&((1<<36)-1))!=GETTER:raise ValueError('Model getter differs')
    for va,words in [(SET_HCI,[0xd0003928,0x390cb900,0xd65f03c0]),(SET_VENDOR,[0xd0003928,0x390cb500,0xd65f03c0])]:
        if image.original[image.offset(va):image.offset(va)+12]!=struct.pack('<3I',*words):raise ValueError('Scan setter differs')
    start=image.cursor;target=SUPPORT+37
    get=image.emit('extended_scan_support',[
        address(start,8,target)[0],0x39400000|((target&4095)<<10)|(8<<5)|9,
        0x121b0529, # and w9,w9,#0x60
        0x7101813f, # cmp w9,#0x60
        0x1a9f17e0, # cset w0,eq
        0xd65f03c0])
    image.put(GETTER,[branch(GETTER,get)],[0xb942a808])
    start=image.cursor
    put=image.emit('extended_scan_publish',[
        0xa9bf7bf3,lambda pc:branch(pc,get,True),0xa8c17bf3,
        address(start+12,8,CACHE)[0],0x39000000|((CACHE&4095)<<10)|(8<<5),
        address(start+20,8,LOWER)[0],lambda pc:branch(pc,SET_HCI+4)])
    image.put(SET_HCI,[branch(SET_HCI,put)],[0xd0003928])
    image.put(SET_VENDOR+4,[0x390cb51f],[0x390cb500])
    return image


def apply(image):
    from Native17 import cbnz
    from Native17Completion import DONE
    from Native17ScanObserve import replace_owned_word
    scan(image);marker=image.entries['native_init_result'];start=image.cursor
    observe=image.emit('scan_before_observation',[
        0xa9bf7bf3,0xaa0003f3,lambda pc:cbnz(pc,0,start+16),
        lambda pc:branch(pc,SET_HCI,True),0xaa1303e0,0xa8c17bf3,
        lambda pc:branch(pc,marker)])
    replace_owned_word(image,DONE,branch(DONE,marker),branch(DONE,observe))
    replace_owned_word(image,marker+24,0x52800003,address(marker+24,3,SUPPORT)[0],True)
    return image

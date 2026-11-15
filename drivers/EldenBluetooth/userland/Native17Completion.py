"""Use the actual support bit and report the original native init completion."""
import struct
from Native17 import BASE,branch,mov,address
from Native17Optional import apply as optional
DONE=BASE+0x182be4
STEP=BASE+0x1840a0
SUPPORT=BASE+0x945820
CONTEXT=BASE+0x930de8
CHAIN_NEXT=BASE+0x23e1f0
MARKER=0xfe700020
def apply(image):
    optional(image)
    descriptor=image.offset(BASE+0x925dc0+0x7c*24)
    if struct.unpack_from('<HH',image.original,descriptor+2)!=(0x0c5b,0x1208):raise ValueError('Optional descriptor differs')
    start=image.cursor
    words=[0xa9bf7bf3,0xaa0003f3,mov(0,MARKER&0xffff),0x72a00000|((MARKER>>16)<<5),
           mov(1,1),0xaa1303e2,mov(3,0),mov(4,0x4843),0xd2800000|(179<<5)|16,0xd4001001,
           0xaa1303e0,0xa8c17bf3,0x7100001f,lambda pc:branch(pc,DONE+4)]
    done=image.emit('native_init_result',words)
    image.put(DONE,[branch(DONE,done)],[0x7100001f])
    start=image.cursor;target=SUPPORT+18
    adrp16=address(start,16,target)[0];adrp8=address(start+20,8,CONTEXT)[0]
    def tbz(pc):
        delta=(start+20-pc)//4
        return 0x36180010|((delta&0x3fff)<<5)
    gate=image.emit('optional_supported_0c5b',[adrp16,0x39400000|((target&4095)<<10)|(16<<5)|16,
        tbz,0xd100c3ff,lambda pc:branch(pc,STEP+4),adrp8,
        0xf9400000|(((CONTEXT&4095)//8)<<10)|(8<<5),lambda pc:branch(pc,CHAIN_NEXT)])
    image.put(STEP,[branch(STEP,gate)],[0xd100c3ff])
    return image

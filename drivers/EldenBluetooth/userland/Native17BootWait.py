"""Wait for the real bootstrap publication before the original address lookup."""
import struct
from Native17 import BASE,branch,mov,address,cbnz
from Native17ScanRoles import apply as roles
SITE=BASE+0x99c20
LOOKUP=BASE+0x9abc0
SYSCTL=BASE+0x709d30
USLEEP=BASE+0x709d9c
MARKER=0xfe700026
TRIES=1200

def apply(image):
    roles(image)
    value=b'kern.elden_bt_bootstrap\0';value+=bytes((-len(value))%4)
    name=image.emit('bootstrap_wait_name',list(struct.unpack('<'+'I'*(len(value)//4),value)))
    start=image.cursor;words=[];labels={};jumps=[]
    def label(n):labels[n]=len(words)
    def jump(kind,n,reg=0):jumps.append((len(words),kind,n,reg));words.append(0)
    words += [0xd10143ff,0xa90353f3,0xa9047bfd,0x910103fd,0xaa0003f3,mov(20,TRIES),mov(8,6),0xb9002be8]
    label('poll')
    words += [mov(8,32),0xf90013e8]
    words += address(start+len(words)*4,0,name)
    words += [0x910003e1,0x910083e2,0xaa1f03e3,0xaa1f03e4,lambda pc:branch(pc,SYSCTL,True)]
    jump('cbnz','sleep',0)
    words += [0xf94013e8,0xf100811f];jump('ne','sleep')
    words += [0xb94003e8,0x7100051f];jump('ne','sleep')
    words += [0xb94007e8,0xb9002be8,0x7100091f];jump('eq','done')
    words += [0x71000d1f];jump('hs','done')
    label('sleep');words += [mov(0,0x86a0),0x72a00020,lambda pc:branch(pc,USLEEP,True),0x71000694];jump('ne','poll')
    label('done')
    words += [mov(0,MARKER&0xffff),0x72a00000|((MARKER>>16)<<5),mov(1,1),mov(2,TRIES),0x4b140042,0xb9402be3,mov(4,0x4843),0xd2800000|(179<<5)|16,0xd4001001,
              0xaa1303e0,0xa9447bfd,0xa94353f3,0x910143ff,lambda pc:branch(pc,LOOKUP)]
    for index,kind,target,reg in jumps:
        pc=start+index*4;dest=start+labels[target]*4
        if kind=='cbnz':words[index]=cbnz(pc,reg,dest)
        else:words[index]=0x54000000|((((dest-pc)//4)&0x7ffff)<<5)|{'eq':0,'ne':1,'hs':2}[kind]
    wait=image.emit('wait_for_real_address',words)
    image.put(SITE,[branch(SITE,wait,True)],[branch(SITE,LOOKUP,True)])
    return image

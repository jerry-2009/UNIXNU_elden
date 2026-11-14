"""Wait on the same IOKit address property that the original daemon reads."""
from Native17 import BASE,branch,mov,address,cbnz
from Native17ScanRoles import apply as roles
SITE=BASE+0x99c20;LOOKUP=BASE+0x9abc0
NAME_MATCH=BASE+0x707f9c;GET_SERVICE=BASE+0x707f78;SEARCH=BASE+0x707f3c
DATA_TYPE=BASE+0x707528;TYPE_ID=BASE+0x707684;DATA_LENGTH=BASE+0x70751c;DATA_BYTES=BASE+0x707510
CF_RELEASE=BASE+0x7077d4;IO_RELEASE=BASE+0x707e10;USLEEP=BASE+0x709d9c
PLANE=BASE+0x77dcf0;KEY=BASE+0x8f7878;MARKER=0xfe700028;TRIES=240

def apply(image):
    roles(image);start=image.cursor;words=[];labels={};jumps=[]
    def label(n):labels[n]=len(words)
    def jump(kind,n,reg=0):jumps.append((len(words),kind,n,reg));words.append(0)
    def call(target):words.append(lambda pc:branch(pc,target,True))
    words += [0xd10143ff,0xa90153f3,0xa9025bf5,0xa90363f7,0xa9047bfd,0x910103fd,0xaa0003f3,mov(20,TRIES),mov(23,0)]
    call(DATA_TYPE);words += [0xaa0003f8]
    label('poll');words += [0xaa1303e0];call(NAME_MATCH);jump('cbz','sleep',0)
    words += [0xaa0003e1,mov(0,0)];call(GET_SERVICE);jump('cbzw','sleep',0)
    words += [0x2a0003f5]+address(start+len(words)*4+4,1,PLANE)
    words += address(start+len(words)*4,2,KEY)+[0xaa1f03e3,mov(4,1)];call(SEARCH)
    words += [0xaa0003f6];jump('cbz','release_io',0);call(TYPE_ID)
    words += [0xeb18001f];jump('ne','release_data')
    words += [0xaa1603e0];call(DATA_LENGTH);words += [0xf100181f];jump('lt','release_data')
    words += [0xaa1603e0,0xaa1f03e1,mov(2,6),0x910003e3];call(DATA_BYTES)
    words += [0xb94003e8,0x79400be9,0x2a090108,0x7100011f,0x1a9f07f7]
    label('release_data');words += [0xaa1603e0];call(CF_RELEASE)
    label('release_io');words += [0xaa1503e0];call(IO_RELEASE);jump('cbnz','done',23)
    label('sleep');words += [mov(0,0xa120),0x72a000e0];call(USLEEP);words += [0x71000694];jump('ne','poll')
    label('done');words += [mov(0,MARKER&0xffff),0x72a00000|((MARKER>>16)<<5),mov(1,1),mov(2,TRIES),0x4b140042,0xaa1703e3,mov(4,0x4843),0xd2800000|(179<<5)|16,0xd4001001,
        0xaa1303e0,0xa9447bfd,0xa94363f7,0xa9425bf5,0xa94153f3,0x910143ff,lambda pc:branch(pc,LOOKUP)]
    for i,kind,target,reg in jumps:
        pc=start+i*4;dest=start+labels[target]*4
        if kind in ('cbz','cbzw','cbnz'):
            word=cbnz(pc,reg,dest);words[i]=word if kind=='cbnz' else word&~0x01000000
            # Pointer tests use X0 rather than truncating a CF object address.
            if kind=='cbz':words[i]|=0x80000000
        else:words[i]=0x54000000|((((dest-pc)//4)&0x7ffff)<<5)|{'ne':1,'lt':11}[kind]
    wait=image.emit('wait_for_address_property',words)
    image.put(SITE,[branch(SITE,wait,True)],[branch(SITE,LOOKUP,True)])
    return image

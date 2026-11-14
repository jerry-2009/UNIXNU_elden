"""Execute the IOKit property wait and verify reference/port ownership."""
from pathlib import Path
import argparse,json,sys
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_INTR,UC_PROT_ALL
import unicorn.arm64_const as r
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenBluetooth/userland'))
from Native17 import Image,BASE
import Native17AddressWait as n

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('original',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);im=n.apply(Image(a.original).routing());rows=[]
    scenarios=[('ready',['ready']),('delayed',['missing','null','zero','ready']),('bad-type',['type','ready']),('short',['short','ready']),('negative',['negative','ready']),('alloc',['alloc','ready']),('timeout',['zero']),('no-service',['missing'])]
    for slide in (0,0x28000000):
        for name,states in scenarios:
            u=Uc(UC_ARCH_ARM64,UC_MODE_ARM);u.mem_map(BASE+slide,0xa00000,UC_PROT_ALL);u.mem_map(0x300000000,0x20000,UC_PROT_ALL)
            for seg,va,vs,fo,fs,prot in im.segments:
                if seg!='__PAGEZERO':u.mem_write(va+slide,bytes(im.data[fo:fo+fs]))
            sp=0x30001e000;arg=0x300001000;dictionary=0x300002000;data=0x300000000
            counts=dict(polls=0,dicts=0,consumed=0,ports=0,released=0,data=0,freed=0,sleeps=0,lookup=0);current=[''];markers=[];done=[]
            u.mem_write(arg,b'bluetooth\0');u.reg_write(r.UC_ARM64_REG_SP,sp);u.reg_write(r.UC_ARM64_REG_X0,arg)
            saved={getattr(r,'UC_ARM64_REG_X'+str(i)):0xabcd0000+i for i in range(19,30)}
            for reg,value in saved.items():u.reg_write(reg,value)
            def ret(e,value=0):e.reg_write(r.UC_ARM64_REG_X0,value&0xffffffffffffffff);e.reg_write(r.UC_ARM64_REG_PC,e.reg_read(r.UC_ARM64_REG_LR))
            def hook(e,pc,size,_):
                if pc==n.SITE+4+slide:done.append(True);e.emu_stop();return
                va=pc-slide
                if va==n.DATA_TYPE:ret(e,9)
                elif va==n.NAME_MATCH:
                    assert e.reg_read(r.UC_ARM64_REG_X0)==arg;current[0]=states[min(counts['polls'],len(states)-1)];counts['polls']+=1
                    if current[0]=='alloc':ret(e,0)
                    else:counts['dicts']+=1;ret(e,dictionary)
                elif va==n.GET_SERVICE:
                    assert e.reg_read(r.UC_ARM64_REG_X0)==0 and e.reg_read(r.UC_ARM64_REG_X1)==dictionary;counts['consumed']+=1
                    if current[0]=='missing':ret(e,0xdeadbeef00000000) # uint32_t return's upper half is unspecified
                    else:counts['ports']+=1;ret(e,0xdeadbeef00001234)
                elif va==n.SEARCH:
                    assert e.reg_read(r.UC_ARM64_REG_W0)==0x1234 and e.reg_read(r.UC_ARM64_REG_X1)==n.PLANE+slide and e.reg_read(r.UC_ARM64_REG_X2)==n.KEY+slide
                    assert e.reg_read(r.UC_ARM64_REG_X3)==0 and e.reg_read(r.UC_ARM64_REG_X4)==1
                    if current[0]=='null':ret(e,0)
                    else:counts['data']+=1;ret(e,data)
                elif va==n.TYPE_ID:assert e.reg_read(r.UC_ARM64_REG_X0)==data;ret(e,8 if current[0]=='type' else 9)
                elif va==n.DATA_LENGTH:assert e.reg_read(r.UC_ARM64_REG_X0)==data;ret(e,-1 if current[0]=='negative' else 5 if current[0]=='short' else 6)
                elif va==n.DATA_BYTES:
                    assert e.reg_read(r.UC_ARM64_REG_X0)==data and e.reg_read(r.UC_ARM64_REG_X1)==0 and e.reg_read(r.UC_ARM64_REG_X2)==6
                    e.mem_write(e.reg_read(r.UC_ARM64_REG_X3),bytes(6) if current[0]=='zero' else bytes([0,0,0,0,0,1]));ret(e)
                elif va==n.CF_RELEASE:assert e.reg_read(r.UC_ARM64_REG_X0)==data;counts['freed']+=1;ret(e)
                elif va==n.IO_RELEASE:assert e.reg_read(r.UC_ARM64_REG_X0)==0x1234;counts['released']+=1;ret(e)
                elif va==n.USLEEP:assert e.reg_read(r.UC_ARM64_REG_X0)==500000;counts['sleeps']+=1;ret(e)
                elif va==n.LOOKUP:
                    counts['lookup']+=1;assert e.reg_read(r.UC_ARM64_REG_X0)==arg and e.reg_read(r.UC_ARM64_REG_SP)==sp
                    assert all(e.reg_read(reg)==value for reg,value in saved.items());ret(e,int(current[0]=='ready'))
            def svc(e,number,_):
                assert e.reg_read(r.UC_ARM64_REG_X16)==179;markers.append([e.reg_read(getattr(r,'UC_ARM64_REG_X'+str(i))) for i in range(5)]);e.reg_write(r.UC_ARM64_REG_X0,0xbeef)
            u.hook_add(UC_HOOK_CODE,hook);u.hook_add(UC_HOOK_INTR,svc);u.emu_start(n.SITE+slide,0,count=30000)
            ready=states[-1]=='ready';sleeps=len(states)-1 if ready else n.TRIES
            assert done and counts['lookup']==1 and counts['sleeps']==sleeps and counts['polls']==(len(states) if ready else n.TRIES)
            assert counts['dicts']==counts['consumed'] and counts['ports']==counts['released'] and counts['data']==counts['freed']
            assert markers==[[n.MARKER,1,sleeps,int(ready),0x4843]];assert u.reg_read(r.UC_ARM64_REG_X0)==int(ready)
            rows.append(dict(scenario=name,slide=slide,**counts))
    (a.output/'result.json').write_text(json.dumps({'passed':True,'cases':len(rows),'actual_instructions':True,'matching_ownership_verified':True,'external_iokit_modeled':True,'records':rows},indent=2)+'\n');print('PASS '+str(len(rows))+' IOKit wait/ownership cases')
if __name__=='__main__':main()

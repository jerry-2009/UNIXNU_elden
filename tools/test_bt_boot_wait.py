"""Execute the actual bounded bootstrap wait and original lookup call boundary."""
from pathlib import Path
import argparse,json,struct,sys
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_INTR,UC_PROT_ALL
import unicorn.arm64_const as r
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenBluetooth/userland'))
from Native17 import Image,BASE
from Native17BootWait import apply,SITE,SYSCTL,USLEEP,LOOKUP,MARKER,TRIES

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('original',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);im=apply(Image(a.original).routing());results=[]
    scenarios=[('ready',[2],False),('starting-ready',[1,1,2],False),('unavailable-ready',[0,1,2],False),('failed',[4],False),('stopped',[3],False),('stopping',[5],False),('timeout',[1],True),('read-error',['error'],True),('size-error',['size'],True),('version-error',['version'],True),('error-ready',['error',2],False)]
    for slide in (0,0x28000000):
        for name,states,timeout in scenarios:
            u=Uc(UC_ARCH_ARM64,UC_MODE_ARM);u.mem_map(BASE+slide,0xa00000,UC_PROT_ALL);u.mem_map(0x300000000,0x20000,UC_PROT_ALL)
            for seg,va,vs,fo,fs,prot in im.segments:
                if seg!='__PAGEZERO':u.mem_write(va+slide,bytes(im.data[fo:fo+fs]))
            sp=0x30001e000;argument=0x300001000;calls=[];sleeps=[];markers=[];lookups=[];done=[]
            u.mem_write(argument,b'bluetooth\0');u.reg_write(r.UC_ARM64_REG_SP,sp);u.reg_write(r.UC_ARM64_REG_X0,argument)
            saved={getattr(r,'UC_ARM64_REG_X'+str(i)):0xabc000+i for i in range(19,30)}
            for reg,value in saved.items():u.reg_write(reg,value)
            def ret(e,value=0):e.reg_write(r.UC_ARM64_REG_X0,value);e.reg_write(r.UC_ARM64_REG_PC,e.reg_read(r.UC_ARM64_REG_LR))
            def hook(e,pc,size,_):
                if pc==SITE+4+slide:done.append(True);e.emu_stop();return
                if pc==SYSCTL+slide:
                    ptr=e.reg_read(r.UC_ARM64_REG_X0);key=b'kern.elden_bt_bootstrap\0';assert bytes(e.mem_read(ptr,len(key)))==key
                    out=e.reg_read(r.UC_ARM64_REG_X1);length=e.reg_read(r.UC_ARM64_REG_X2)
                    assert struct.unpack('<Q',e.mem_read(length,8))[0]==32 and not e.reg_read(r.UC_ARM64_REG_X3) and not e.reg_read(r.UC_ARM64_REG_X4)
                    state=states[min(len(calls),len(states)-1)];calls.append(state)
                    if state=='error':ret(e,0xffffffff);return
                    e.mem_write(out,struct.pack('<IIQHHI6sH',2 if state=='version' else 1,1 if isinstance(state,str) else state,1,0x1d,0x80ab,0,b'abcdef',0));e.mem_write(length,struct.pack('<Q',16 if state=='size' else 32));ret(e)
                elif pc==USLEEP+slide:
                    assert e.reg_read(r.UC_ARM64_REG_X0)==100000;sleeps.append(1);ret(e)
                elif pc==LOOKUP+slide:
                    lookups.append(True);assert e.reg_read(r.UC_ARM64_REG_X0)==argument and e.reg_read(r.UC_ARM64_REG_SP)==sp
                    assert all(e.reg_read(reg)==value for reg,value in saved.items());ret(e,1 if calls[-1]==2 else 0)
            def svc(e,number,_):
                assert e.reg_read(r.UC_ARM64_REG_X16)==179
                markers.append([e.reg_read(getattr(r,'UC_ARM64_REG_X'+str(i))) for i in range(5)]);retvalue=0xdead;e.reg_write(r.UC_ARM64_REG_X0,retvalue)
            u.hook_add(UC_HOOK_CODE,hook);u.hook_add(UC_HOOK_INTR,svc);u.emu_start(SITE+slide,0,count=60000)
            expected_sleeps=TRIES if timeout else len(states)-1
            expected_state=6 if timeout and isinstance(states[-1],str) else states[-1]
            assert done and len(lookups)==1 and len(sleeps)==expected_sleeps and len(calls)==(TRIES if timeout else len(states))
            assert markers==[[MARKER,1,expected_sleeps,expected_state,0x4843]],(name,markers)
            assert u.reg_read(r.UC_ARM64_REG_X0)==(1 if states[-1]==2 else 0)
            results.append({'scenario':name,'slide':slide,'calls':len(calls),'sleeps':len(sleeps),'state':expected_state,'real_lookup_called_once':True})
    (a.output/'result.json').write_text(json.dumps({'passed':True,'cases':len(results),'actual_instructions':True,'sysctl_sleep_lookup_modeled':True,'records':results},indent=2)+'\n');print('PASS '+str(len(results))+' bootstrap wait cases')
if __name__=='__main__':main()

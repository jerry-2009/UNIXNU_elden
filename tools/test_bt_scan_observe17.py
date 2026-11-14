"""Reproduce pre-discovery cache initialization, then run the real completion."""
from pathlib import Path
import argparse,json,struct,sys
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_INTR,UC_PROT_ALL
import unicorn.arm64_const as r
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenBluetooth/userland'))
from Native17 import Image,BASE
from Native17Scan import SET_HCI,CACHE,LOWER,SUPPORT
from Native17ScanReady import apply as old
from Native17ScanObserve import apply as patched
from Native17Completion import DONE,CONTEXT,MARKER

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('original',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);rows=[]
    for slide in (0,0x28000000):
        for label,derive in [('v134',old),('observe',patched)]:
            im=derive(Image(a.original).routing())
            for status in (0,1,0x274):
                for bits in (0,0x20,0x40,0x60,0xff):
                    u=Uc(UC_ARCH_ARM64,UC_MODE_ARM);u.mem_map(BASE+slide,0xa00000,UC_PROT_ALL);u.mem_map(0x300000000,0x20000,UC_PROT_ALL)
                    for seg,va,vs,fo,fs,prot in im.segments:
                        if seg!='__PAGEZERO':u.mem_write(va+slide,bytes(im.data[fo:fo+fs]))
                    stop=0x30001f000;sp=0x30001e000;seen=[];ends=[]
                    def hook(e,pc,size,_):
                        if pc==stop:ends.append(True);e.emu_stop()
                    def svc(e,number,_):
                        seen.append([e.reg_read(getattr(r,'UC_ARM64_REG_X'+str(i))) for i in range(5)])
                        expected_at_marker=int(label=='observe' and status==0 and bits&0x60==0x60)
                        assert bytes(e.mem_read(CACHE+slide,1))==bytes([expected_at_marker])
                        assert bytes(e.mem_read(LOWER+slide,1))==bytes([expected_at_marker])
                        e.reg_write(r.UC_ARM64_REG_X0,0xdead)
                    u.hook_add(UC_HOOK_CODE,hook);u.hook_add(UC_HOOK_INTR,svc)
                    u.reg_write(r.UC_ARM64_REG_SP,sp);u.reg_write(r.UC_ARM64_REG_LR,stop);u.reg_write(r.UC_ARM64_REG_X0,1)
                    u.mem_write(SUPPORT+37+slide,b'\0');u.emu_start(SET_HCI+slide,0,count=50)
                    assert ends and bytes(u.mem_read(LOWER+slide,1))==b'\0';ends.clear()
                    u.mem_write(SUPPORT+37+slide,bytes([bits]));u.mem_write(CONTEXT+slide,struct.pack('<Q',0x300001000))
                    u.reg_write(r.UC_ARM64_REG_X0,status);u.reg_write(r.UC_ARM64_REG_LR,stop)
                    for i in range(19,30):u.reg_write(getattr(r,'UC_ARM64_REG_X'+str(i)),0xabcdef00+i)
                    u.emu_start(DONE+slide,0,count=150)
                    expected=int(status==0 and bits&0x60==0x60)
                    assert ends and seen==[[MARKER,1,status,((SUPPORT&~4095)+slide) if label=='observe' else 0,0x4843]]
                    assert bytes(u.mem_read(CACHE+slide,1))==bytes([expected]) and bytes(u.mem_read(LOWER+slide,1))==bytes([expected])
                    assert u.reg_read(r.UC_ARM64_REG_X0)==status and u.reg_read(r.UC_ARM64_REG_SP)==sp and u.reg_read(r.UC_ARM64_REG_LR)==stop
                    assert all(u.reg_read(getattr(r,'UC_ARM64_REG_X'+str(i)))==0xabcdef00+i for i in range(19,30))
                    assert bytes(u.mem_read(CONTEXT+slide,8))==bytes(8)
                    assert struct.unpack('<I',u.mem_read(BASE+slide+0x945800,4))[0]==(2 if status==0 else 3)
                    rows.append({'version':label,'slide':slide,'status':status,'support37':bits,'published':expected})
    (a.output/'result.json').write_text(json.dumps({'passed':True,'cases':len(rows),'observed_after_publication':True,'hardware_cause_proven':False,'records':rows},indent=2)+'\n');print('PASS '+str(len(rows))+' actual discovery-timing cases')
if __name__=='__main__':main()

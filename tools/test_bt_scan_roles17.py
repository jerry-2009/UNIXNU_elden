"""Execute native scan parameter/enable senders through their actual submit call."""
from pathlib import Path
import argparse,json,struct,sys
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE,UC_PROT_ALL
import unicorn.arm64_const as r
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenBluetooth/userland'))
from Native17 import Image,BASE
import Native17ScanObserve as old
import Native17ScanRoles as fixed
from Native17Completion import SUPPORT

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('original',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);rows=[]
    for slide in (0,0x28000000):
        for name,mod,setter,disable in [('v135',old,BASE+0x216f34,BASE+0x216ee0),('fixed',fixed,fixed.SET_HCI,fixed.SET_VENDOR)]:
            im=mod.apply(Image(a.original).routing())
            for bits in (0,0x20,0x40,0x60,0xff):
                for kind,entry in [('parameters',0x78a58),('refresh',0x67ef4),('enable',0x782fc)]:
                    u=Uc(UC_ARCH_ARM64,UC_MODE_ARM);u.mem_map(BASE+slide,0xa00000,UC_PROT_ALL);u.mem_map(0x300000000,0x20000,UC_PROT_ALL)
                    for seg,va,vs,fo,fs,prot in im.segments:
                        if seg!='__PAGEZERO':u.mem_write(va+slide,bytes(im.data[fo:fo+fs]))
                    sp=0x30001e000;fp=sp+0x100;stop=0x30001f000;sent=[]
                    def hook(e,pc,size,_):
                        if pc==stop:e.emu_stop()
                        elif pc==BASE+slide+0x50934:
                            sent.append((e.reg_read(r.UC_ARM64_REG_W0),e.reg_read(r.UC_ARM64_REG_X1)));e.emu_stop()
                        elif pc in (BASE+slide+0x7eb8,BASE+slide+0xd0d4):sent.append(('vendor',pc-slide));e.emu_stop()
                    u.hook_add(UC_HOOK_CODE,hook);u.reg_write(r.UC_ARM64_REG_SP,sp);u.reg_write(r.UC_ARM64_REG_LR,stop)
                    u.mem_write(SUPPORT+37+slide,bytes([bits]));u.reg_write(r.UC_ARM64_REG_X0,0);u.emu_start(disable+slide,0,count=50)
                    u.reg_write(r.UC_ARM64_REG_X0,0);u.reg_write(r.UC_ARM64_REG_LR,stop);u.emu_start(setter+slide,0,count=50)
                    u.reg_write(r.UC_ARM64_REG_FP,fp);u.reg_write(r.UC_ARM64_REG_X8,0x10);u.reg_write(r.UC_ARM64_REG_X9,0)
                    u.reg_write(r.UC_ARM64_REG_X10,0);u.reg_write(r.UC_ARM64_REG_X11,1);u.reg_write(r.UC_ARM64_REG_X12,0)
                    u.reg_write(r.UC_ARM64_REG_X21,0x10);u.reg_write(r.UC_ARM64_REG_X22,0x20);u.reg_write(r.UC_ARM64_REG_X23,1)
                    u.mem_write(fp-0x60,b'\x01');u.mem_write(fp-0x63,b'\x01'*3);u.mem_write(fp-0x6a,struct.pack('<3H',0x20,0x20,0x20));u.mem_write(sp+0x70,struct.pack('<3H',0x10,0x10,0x10));u.mem_write(sp+0x60,bytes(8))
                    u.mem_write(fp-0x28,b'\x01');u.mem_write(fp-0x29,b'\x01');u.mem_write(fp-0x2c,struct.pack('<H',0x20));u.mem_write(fp-0x2e,struct.pack('<H',0x10));u.mem_write(BASE+slide+0x93c30d,b'\0\x01')
                    if kind=='refresh':u.reg_write(r.UC_ARM64_REG_X10,0x20)
                    u.emu_start(BASE+slide+entry,0,count=120)
                    support=bits&0x60==0x60
                    expected='vendor' if name=='v135' and support and kind=='enable' else (0xd8 if kind=='enable' else 0xd7) if name=='fixed' and support else (0xac if kind=='enable' else 0xab)
                    assert sent and sent[0][0]==expected,(name,kind,bits,sent,hex(u.reg_read(r.UC_ARM64_REG_PC)))
                    if expected in (0xab,0xd7):
                        assert sent[0][1]==BASE+slide+(0x68120 if kind=='refresh' else 0x67640)
                    if expected==0xd7:
                        args=struct.unpack('<6Q',u.mem_read(sp,48));assert args[:3]==(1,0,1),args
                        assert bytes(u.mem_read(args[3],1))==b'\1';assert bytes(u.mem_read(args[4],2))==struct.pack('<H',0x20);assert bytes(u.mem_read(args[5],2))==struct.pack('<H',0x10)
                    rows.append({'variant':name,'slide':slide,'support37':bits,'path':kind,'submitted':expected})
    (a.output/'result.json').write_text(json.dumps({'passed':True,'cases':len(rows),'actual_native_submit_selection':True,'scan_payload_and_callback_checked':True,'old_roles_reproduce_legacy_vendor_paths':True,'records':rows},indent=2)+'\n');print('PASS '+str(len(rows))+' native scan send-path cases')
if __name__=='__main__':main()

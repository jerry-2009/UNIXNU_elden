"""Execute the exact scan getter/setters and native command-selector branch."""
from pathlib import Path
import argparse,hashlib,json,struct,sys
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE,UC_PROT_ALL
import unicorn.arm64_const as r
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenBluetooth/userland'))
from Native17 import Image,BASE
from Native17Scan import apply,GETTER,SET_HCI,SET_VENDOR,CACHE,LOWER,VENDOR,SUPPORT

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('original',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    im=apply(Image(a.original).routing());cases=0
    for slide in (0,0x28000000):
        u=Uc(UC_ARCH_ARM64,UC_MODE_ARM);u.mem_map(BASE+slide,0xa00000,UC_PROT_ALL);u.mem_map(0x300000000,0x20000,UC_PROT_ALL)
        for seg,va,vs,fo,fs,prot in im.segments:
            if seg!='__PAGEZERO':u.mem_write(va+slide,bytes(im.data[fo:fo+fs]))
        stop=0x30001f000;sp=0x30001e000;hits=[]
        def hook(e,pc,size,_):
            if pc in (stop,BASE+slide+0x67728,BASE+slide+0x677cc):
                hits.append(pc);e.emu_stop()
        # Exact selection addresses are 0x100067728 / 0x1000677cc.
        u.hook_add(UC_HOOK_CODE,hook)
        for bits in range(256):
            expected=int(bits&0x60==0x60);u.mem_write(SUPPORT+37+slide,bytes([bits]))
            for entry in (GETTER,SET_HCI):
                hits.clear();u.reg_write(r.UC_ARM64_REG_SP,sp);u.reg_write(r.UC_ARM64_REG_LR,stop);u.reg_write(r.UC_ARM64_REG_X0,bits&1)
                saved={getattr(r,'UC_ARM64_REG_X'+str(i)):0xabcd0000+i for i in range(19,30)}
                for reg,value in saved.items():u.reg_write(reg,value)
                u.mem_write(CACHE+slide,b'\xa5');u.mem_write(LOWER+slide,b'\x5a')
                u.emu_start(entry+slide,0,count=50)
                assert hits==[stop] and u.reg_read(r.UC_ARM64_REG_W0)==expected
                assert u.reg_read(r.UC_ARM64_REG_SP)==sp and u.reg_read(r.UC_ARM64_REG_LR)==stop
                assert all(u.reg_read(reg)==value for reg,value in saved.items())
                assert bytes(u.mem_read(CACHE+slide,1))==(bytes([expected]) if entry==SET_HCI else b'\xa5')
                assert bytes(u.mem_read(LOWER+slide,1))==(bytes([expected]) if entry==SET_HCI else b'\x5a')
                cases+=1
            # The just-published flag selects native legacy or extended code.
            hits.clear();u.emu_start(BASE+slide+0x6771c,0,count=8)
            assert hits==[BASE+slide+(0x67728 if expected else 0x677cc)]
            cases+=1
        for argument in (0,1):
            hits.clear();u.reg_write(r.UC_ARM64_REG_X0,argument);u.reg_write(r.UC_ARM64_REG_LR,stop);u.mem_write(VENDOR+slide,b'\x01')
            u.emu_start(SET_VENDOR+slide,0,count=8);assert hits==[stop] and bytes(u.mem_read(VENDOR+slide,1))==b'\0';cases+=1
    result={'passed':True,'cases':cases,'all_support_byte_values':True,'slides':2,'actual_native_instructions':True,'external_controller_not_emulated':True,'source_sha256':hashlib.sha256((ROOT/'drivers/EldenBluetooth/userland/Native17Scan.py').read_bytes()).hexdigest()}
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()

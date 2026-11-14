"""Run the actual optional callbacks at two ASLR slides with logging/chain doubles."""
from pathlib import Path
import argparse,json,struct,sys
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE,UC_PROT_ALL
from unicorn.arm64_const import *
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenBluetooth/userland'))
from Native17 import Image,BASE
from Native17Optional import apply
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('original',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--complete',action='store_true');a=p.parse_args();o=a.output.resolve();o.mkdir(parents=True,exist_ok=False)
    patch=apply
    if a.complete:
        from Native17Completion import apply as patch
    callbacks=[('host_buffer',BASE+0x184c08,BASE+0x7a8218),('host_flow',BASE+0x184c84,BASE+0x7a8293),('erroneous_data',BASE+0x184cf4,BASE+0x7a8302)]
    results=[]
    for slide in (0,0x28000000):
        for label,image in [('original',Image(a.original)),('patched',patch(Image(a.original).routing()))]:
            for name,entry,chain_name in callbacks:
                for status in (0,1,0x2bd,0x2cd,0x2ce,0xffffffff):
                    for logging in (0,1):
                        u=Uc(UC_ARCH_ARM64,UC_MODE_ARM);u.mem_map(BASE+slide,0xa00000,UC_PROT_ALL)
                        for seg,va,vs,fo,fs,prot in image.segments:
                            if seg!='__PAGEZERO':u.mem_write(va+slide,bytes(image.data[fo:fo+fs]))
                        u.mem_map(0x300000000,0x20000,UC_PROT_ALL);sp=0x30001e000;stop=0x30001f000
                        u.reg_write(UC_ARM64_REG_SP,sp);u.reg_write(UC_ARM64_REG_LR,stop);u.reg_write(UC_ARM64_REG_W0,status);u.reg_write(UC_ARM64_REG_CPACR_EL1,3<<20)
                        u.mem_write(BASE+slide+0x8cd2d8,struct.pack('<Q',0x300001000));u.mem_write(0x300001000,struct.pack('<Q',0x1122334455667788))
                        saved=[]
                        for i in range(19,30):
                            reg=globals()['UC_ARM64_REG_X'+str(i)];u.reg_write(reg,0xabcdef00+i);saved.append((reg,0xabcdef00+i))
                        observed=[];log_calls=[];ended=[]
                        def ret(emu,value=0):emu.reg_write(UC_ARM64_REG_X0,value);emu.reg_write(UC_ARM64_REG_PC,emu.reg_read(UC_ARM64_REG_LR))
                        def hook(emu,pc,size,_):
                            if pc==stop:ended.append(True);emu.emu_stop();return
                            va=pc-slide
                            if va==BASE+0x181a48:
                                observed.append((emu.reg_read(UC_ARM64_REG_W0),emu.reg_read(UC_ARM64_REG_X1)));ret(emu,0)
                            elif va in (BASE+0x577f4,BASE+0x709778):ret(emu,logging)
                            elif va==BASE+0x567c4:ret(emu,0)
                            elif va in (BASE+0x56854,BASE+0x68d710,BASE+0x68d770,BASE+0x68d7d0):log_calls.append(va);ret(emu,0)
                        u.hook_add(UC_HOOK_CODE,hook);u.emu_start(entry+slide,0,count=2000)
                        expected=0 if label=='patched' or (name=='host_flow' and status==0x2cd) else status
                        assert ended and observed==[(expected,chain_name+slide)],(label,name,status,logging,observed,hex(u.reg_read(UC_ARM64_REG_PC)))
                        assert u.reg_read(UC_ARM64_REG_SP)==sp and all(u.reg_read(reg)==v for reg,v in saved)
                        if status and logging and (label=='patched' or name!='host_flow' or status==0x2cd):assert log_calls
                        results.append({'version':label,'callback':name,'status':status,'logging':logging,'slide':slide,'chain_result':expected})
    (o/'result.json').write_text(json.dumps({'passed':True,'cases':len(results),'actual_callback_instructions':True,'external_logging_and_chain_modeled':True,'records':results},indent=2)+'\n');print('PASS '+str(len(results))+' actual callback cases')
if __name__=='__main__':main()

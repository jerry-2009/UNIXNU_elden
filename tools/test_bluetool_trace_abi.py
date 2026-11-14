"""Execute the real arm64 marker emitter at two loads with a syscall test double."""
from pathlib import Path
import argparse,hashlib,json,struct
from capstone import Cs,CS_ARCH_ARM64,CS_MODE_LITTLE_ENDIAN
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_INTR
from unicorn.arm64_const import UC_ARM64_REG_X0,UC_ARM64_REG_X19,UC_ARM64_REG_X29,UC_ARM64_REG_X30,UC_ARM64_REG_SP,UC_ARM64_REG_PC
import unicorn.arm64_const as reg
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('helper',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();o=a.output.resolve();o.mkdir(parents=True,exist_ok=False)
    b=a.helper.read_bytes();at=32;segments=[];sym=None
    for _ in range(struct.unpack_from('<I',b,16)[0]):
        cmd,n=struct.unpack_from('<II',b,at)
        if cmd==0x19:segments.append(struct.unpack_from('<4Q',b,at+24))
        if cmd==2:sym=struct.unpack_from('<4I',b,at+8)
        at+=n
    addresses=[]
    for i in range(sym[1]):
        name,kind,section,desc,value=struct.unpack_from('<IBBHQ',b,sym[0]+i*16);s=sym[2]+name
        if not kind&0xe0 and b[s:b.index(b'\0',s)]==b'_elden_bt_trace':addresses.append(value)
    assert len(addresses)==1;address=addresses[0]
    vm,vs,fo,fs=next(x for x in segments if x[0]<=address<x[0]+x[3]);start=fo+address-vm
    instructions=[]
    for ins in Cs(CS_ARCH_ARM64,CS_MODE_LITTLE_ENDIAN).disasm(b[start:start+512],address):
        instructions.append(ins)
        if ins.mnemonic=='ret':break
    assert instructions[-1].mnemonic=='ret' and sum(i.mnemonic=='svc' for i in instructions)==1
    code=b[start:start+sum(i.size for i in instructions)];(o/'emitter.asm').write_text('\n'.join(f'{i.address:x}: {i.mnemonic} {i.op_str}' for i in instructions)+'\n')
    registers=[getattr(reg,'UC_ARM64_REG_X'+str(i)) for i in range(31)];cases=0
    for load in (0x10000000,0x30000000):
        for phase in range(1,9):
            for script,error,state,identity in [(1,0,2,1),(2,22,2,0),(3,95,2,0),(0,-1,0xffffffff,1)]:
                u=Uc(UC_ARCH_ARM64,UC_MODE_ARM);u.mem_map(load,4096);u.mem_write(load,code);u.mem_map(0x50000000,0x10000);u.mem_map(0x60000000,4096)
                for i,r in enumerate(registers):u.reg_write(r,0x77000000+i)
                sp=0x50008000;u.reg_write(UC_ARM64_REG_SP,sp);u.reg_write(UC_ARM64_REG_X30,0x60000000)
                for i,v in enumerate((phase,script,error&0xffffffff,state,identity)):u.reg_write(registers[i],v)
                saved=[u.reg_read(r) for r in registers[19:30]];events=[]
                def syscall(uc,number,_):
                    args=[uc.reg_read(r) for r in registers[:5]];assert uc.reg_read(registers[16])==179
                    assert args==[0xfe70001c,phase,error&0xffffffff,script|(state<<8)|(identity<<40),0x42544832],args
                    events.append(args)
                    for i in range(18):uc.reg_write(registers[i],0x12340000+i)
                u.hook_add(UC_HOOK_INTR,syscall);u.emu_start(load,0x60000000,count=200)
                assert len(events)==1 and u.reg_read(UC_ARM64_REG_SP)==sp and [u.reg_read(r) for r in registers[19:30]]==saved
                cases+=1
    r={'passed':True,'cases':cases,'actual_emitter_sha256':hashlib.sha256(code).hexdigest(),'helper_sha256':hashlib.sha256(b).hexdigest(),'loads':2,'syscall_is_test_double':True,'live_kdebug_delivery_unproven':True}
    (o/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
if __name__=='__main__':main()

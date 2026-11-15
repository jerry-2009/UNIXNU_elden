"""Exercise the emitted ARM64 instructions and actual kernel completion/marker bodies."""
from pathlib import Path
import argparse,hashlib,json,struct,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'drivers/EldenBluetooth/userland'),str(ROOT/'drivers/EldenBluetooth')]
from Native17 import Image,BASE
from Native17Completion import apply,DONE,STEP,SUPPORT,CONTEXT,CHAIN_NEXT,MARKER
from NativeInitSource import host

def instructions(original):
    from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_INTR,UC_PROT_ALL
    import unicorn.arm64_const as regs
    def reg(n):return getattr(regs,'UC_ARM64_REG_'+n)
    rows=[]
    def machine(im,slide):
        u=Uc(UC_ARCH_ARM64,UC_MODE_ARM);u.mem_map(BASE+slide,0xa00000,UC_PROT_ALL)
        for seg,va,vs,fo,fs,prot in im.segments:
            if seg!='__PAGEZERO':u.mem_write(va+slide,bytes(im.data[fo:fo+fs]))
        u.mem_map(0x300000000,0x20000,UC_PROT_ALL)
        u.reg_write(reg('SP'),0x30001e000);u.reg_write(reg('LR'),0x30001f000)
        for i in range(19,30):u.reg_write(reg('X'+str(i)),0xabc000+i)
        return u
    def preserved(u,sp):
        assert u.reg_read(reg('SP'))==sp
        assert all(u.reg_read(reg('X'+str(i)))==0xabc000+i for i in range(19,30))
        assert u.reg_read(reg('LR'))==0x30001f000
    for slide in (0,0x28000000):
        for label,im in [('original',Image(original)),('complete',apply(Image(original).routing()))]:
            for status in (0,1,0x274,0xffffffff):
                u=machine(im,slide);u.reg_write(reg('X0'),status)
                u.mem_write(CONTEXT+slide,struct.pack('<Q',0x300001000));seen=[];ended=[]
                def interrupt(e,number,_):
                    seen.append([e.reg_read(reg('X'+str(i))) for i in range(5)])
                    assert e.reg_read(reg('X16'))==179
                    # The syscall may replace caller-saved registers and flags.
                    for i in range(19):e.reg_write(reg('X'+str(i)),0xdead0000+i)
                    e.reg_write(reg('NZCV'),0xf0000000)
                def stop(e,pc,size,_):
                    if pc==0x30001f000:ended.append(True);e.emu_stop()
                u.hook_add(UC_HOOK_INTR,interrupt);u.hook_add(UC_HOOK_CODE,stop)
                u.emu_start(DONE+slide,0,count=150)
                assert ended and seen==([[MARKER,1,status,0,0x4843]] if label=='complete' else [])
                assert u.reg_read(reg('X0'))==status
                assert struct.unpack('<I',u.mem_read(BASE+slide+0x945800,4))[0]==(2 if status==0 else 3)
                assert bytes(u.mem_read(CONTEXT+slide,8))==bytes(8);preserved(u,0x30001e000)
                rows.append({'kind':'completion','version':label,'slide':slide,'status':status})
        im=apply(Image(original).routing())
        for support in (0,8,247,255):
            u=machine(im,slide);u.mem_write(SUPPORT+18+slide,bytes([support]));u.mem_write(CONTEXT+slide,struct.pack('<Q',0x300001000))
            u.reg_write(reg('X0'),0x8765);hits=[]
            def gate_stop(e,pc,size,_):
                if pc-slide in (STEP+4,CHAIN_NEXT):hits.append(pc-slide);e.emu_stop()
            u.hook_add(UC_HOOK_CODE,gate_stop);u.emu_start(STEP+slide,0,count=32)
            assert hits==([STEP+4] if support&8 else [CHAIN_NEXT])
            assert u.reg_read(reg('X0'))==(0x8765 if support&8 else 0x300001000)
            preserved(u,0x30001e000-(0x30 if support&8 else 0))
            rows.append({'kind':'support','slide':slide,'byte18':support,'submitted':bool(support&8)})
    return rows

def host_tests(cxx,out,scan=False):
    derive=host
    if scan:
        from ScanInitSource import host as derive
    function=derive().decode().split('extern "C" int elden_bt_native_init_result',1)[1]
    function='extern "C" int elden_bt_native_init_result'+function
    marker=(ROOT/'drivers/EldenBluetooth/diagnostics/NativeInitMarker.inc').read_text()
    text=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
struct Proc{int pid;uint64_t unique;const char *name;bool hash;};using proc_t=Proc*;
int proc_pid(proc_t p){return p->pid;} uint64_t proc_uniqueid(proc_t p){return p->unique;}
const char *proc_best_name(proc_t p){return p->name;}
int proc_getcdhash(proc_t p,unsigned char *out){const unsigned char h[]={0xfe,0x7b,0xc1,0x82,0x38,0x6a,0x27,0x66,0xc7,0x57,0x4f,0x8b,0x48,0x41,0x2f,0xf9,0xdf,0x11,0x35,0x64};memcpy(out,h,20);out[0]^=!p->hash;return 0;}
enum {PbLinkUp=2};struct Bridge{uint32_t unit,client;int pid,link;bool pending,own_reset,ready,ready_noted;unsigned failed_starts;};
struct Host{int client_pid;uint64_t client_uniqueid;uint32_t client_unit;Bridge bridge;int *lock;bool withdrawing;};
Host *gEldenBtHost;int lock_depth;bool stopping;
void IOLockLock(int*){assert(lock_depth==0);++lock_depth;}void IOLockUnlock(int*){assert(lock_depth==1);--lock_depth;}
bool elden_wcn_stop_requested(){return stopping;}
'''+function+'''
void marker(proc_t p,uint32_t code,uint64_t status,uint64_t mode,uint64_t version,uint64_t magic){
'''+marker+r'''
}
int main(){
 Proc p{79,1234,"bluetoothd",true};Host h{};
 auto reset=[&]{h={79,1234,1,{1,1,79,PbLinkUp,false,false,false,false,17},nullptr,false};gEldenBtHost=&h;stopping=false;};
 for(int fault=0;fault<12;++fault){reset();uint32_t result=0;
  switch(fault){case 1:h.client_pid++;break;case 2:h.client_uniqueid++;break;case 3:h.client_unit++;break;case 4:h.bridge.client=0;break;case 5:h.bridge.pid++;break;case 6:h.bridge.link=0;break;case 7:h.bridge.pending=true;break;case 8:h.bridge.own_reset=true;break;case 9:stopping=true;break;case 10:h.withdrawing=true;break;case 11:result=0x274;break;}
  assert(elden_bt_native_init_result(&p,result)==(fault==0));assert(h.bridge.ready==(fault==0));assert(h.bridge.ready_noted==(fault==0));assert(lock_depth==0);
 }
 reset();assert(elden_bt_native_init_result(nullptr,0)==0);gEldenBtHost=nullptr;assert(elden_bt_native_init_result(&p,0)==0);
 reset();h.bridge.ready=h.bridge.ready_noted=true;assert(!elden_bt_native_init_result(&p,1));assert(!h.bridge.ready&&!h.bridge.ready_noted);
 reset();h.bridge.ready=h.bridge.ready_noted=true;Proc other=p;other.unique++;assert(!elden_bt_native_init_result(&other,1));assert(h.bridge.ready&&h.bridge.ready_noted);
 for(int fault=0;fault<7;++fault){reset();Proc q=p;uint32_t code=0xfe700020;uint64_t version=0,magic=0x4843,status=1;
  switch(fault){case 1:code++;break;case 2:status=2;break;case 3:version=1;break;case 4:magic++;break;case 5:q.name="other";break;case 6:q.hash=false;break;}
  marker(&q,code,status,0,version,magic);assert(h.bridge.ready==(fault==0));
 }
 // Diagnostic log quota must not disable real state updates after 16 restarts.
 for(int i=0;i<24;++i){reset();marker(&p,0xfe700020,1,0,0,0x4843);assert(h.bridge.ready);marker(&p,0xfe700020,1,0x274,0,0x4843);assert(!h.bridge.ready);}
 assert(lock_depth==0);puts("PASS actual completion and marker guards");
}
'''
    if scan:
        anchor='assert(h.bridge.ready_noted==(fault==0));'
        assert text.count(anchor)==1
        text=text.replace(anchor,anchor+'assert(h.bridge.failed_starts==(fault==0?0:17));')
    source=out/'native-init-test.cpp';source.write_text(text);exe=out/'native-init-test'
    subprocess.run([cxx,'-std=c++17','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(source),'-o',str(exe)],check=True)
    r=subprocess.run([str(exe)],capture_output=True);(out/'host.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    return {'passed':True,'actual_function_sha256':hashlib.sha256(function.encode()).hexdigest(),'actual_marker_sha256':hashlib.sha256(marker.encode()).hexdigest(),'asan_ubsan':True}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--original',type=Path);p.add_argument('--cxx');p.add_argument('--scan',action='store_true');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);r={}
    if a.original:r['instructions']=instructions(a.original)
    if a.cxx:r['host']=host_tests(a.cxx,a.output,a.scan)
    assert r;r['passed']=True
    (a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'passed':True,'instruction_cases':len(r.get('instructions',[])),'host':bool(a.cxx)}))
if __name__=='__main__':main()

"""Run actual platform fence/config/MSI/PERST helpers with fault-injected IO."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);d=ROOT/'drivers/EldenPcie'
    s=(d/'TestTransport.cpp').read_text().split('int main(){',1)[0]
    s=s.replace('#include "DmaNative.h"','#include "DmaNative.h"\n#include "PlatformFence.h"\n#include "MhiStop.h"\n#include "Pins.h"')
    s=s.replace('static uint32_t cfg[1024],dbi[1024];','''static uint32_t cfg[1024],dbi[1024],bar[1024],pin_regs[2048];
static uint64_t pending_until;static bool stuck_pending,stuck_pin;static int pin_error;
static unsigned pin_writes;static int thread_token;static void *current_thread(){return &thread_token;}
static void IODelay(unsigned us){clock_us+=us;}''')
    s=s.replace('if(!rc)*v=data[off/4];', 'if(!rc){if(data==cfg&&off==0x48&&pending_until&&clock_us>=pending_until&&!stuck_pending)data[off/4]&=~(32u<<16);*v=data[off/4];}')
    s=s.replace('struct Context {','''struct Context {
    bool runtime_returned=false,runtime_quiesced=false,platform_callback_returned=false,platform_perst_verified=false;
    void *runtime_consumer=nullptr,*runtime_thread=nullptr;
    EldenPlatformFence platform_fence={};EldenMhiStop mhi_stop={};EldenPciePins pins={};Region pin_map;''')
    transport=(d/'TransportNativeRuntime.inc').read_text().replace('if(c->config.master_attempted)return -95;','if(c->config.master_attempted)return platform_dma_ready(c);')
    (out/'TransportNativeRuntime.inc').write_text(transport)
    s=s.replace('#include "TransportNativeRuntime.inc"','''static int platform_dma_ready(Context *);
#include "TransportNativeRuntime.inc"
static Context *runtime_context;static int platform_config_error;
#include "PlatformFenceNative.inc"
static int pin_read(void *,unsigned off,uint32_t *value){assert(off<=0x1008&&!(off&3));*value=pin_regs[off/4];return 0;}
static int pin_write(void *,unsigned off,uint32_t value){assert(off==4);pin_writes++;if(pin_error)return pin_error;pin_regs[1]=(value&~1u)|(stuck_pin?1u:((value>>1)&1));return 0;}
''')
    s+='''
static void prepare(){
    reset();pending_until=0;stuck_pending=stuck_pin=false;pin_error=0;pin_writes=0;platform_config_error=0;
    runtime_context=active;active->runtime_thread=current_thread();active->runtime_returned=true;active->platform_callback_returned=true;
    memset(bar,0,sizeof bar);bar[0x38/4]=2;bar[0x48/4]=0xff04;active->bar0_map.data=bar;
    memset(pin_regs,0,sizeof pin_regs);pin_regs[0]=0x201;pin_regs[1]=3;pin_regs[0x1000/4]=7;
    active->pin_map.data=pin_regs;active->pins={active,pin_read,pin_write,delay,true,false};
    cfg[0x48/4]=0x00100000;transport_run(active);CHECK(active->transport_ready);
    active->config.io.master_ready=allow_master;CHECK(!elden_pcie_cfg_master(&active->config,true));
    active->transport_cleanup=true;stop_requested=1;powered=false;
    active->msi.io.quiesced=[](void *p){return platform_dma_ready((Context *)p);};
}
static void dma_and_msi(){CHECK(!platform_fence_run(active));active->runtime_quiesced=true;CHECK(!elden_pcie_msi_stop(&active->msi,clock_us+100000));}
int main(){
    prepare();unsigned before=calls;CHECK(!platform_fence_run(active));unsigned count=calls-before;
    CHECK(active->platform_fence.phase==3&&active->platform_fence.master_off&&active->platform_fence.transactions_sampled&&active->platform_fence.transactions_idle);
    CHECK((cfg[1]&7)==2&&(cfg[1]&0xffff0000u)==0xa5000000u);
    CHECK(active->mhi_stop.control==2&&active->mhi_stop.status==0xff04&&!active->mhi_stop.reset_observed);
    active->runtime_quiesced=true;CHECK(platform_assert_perst(active,clock_us+10000)==-16&&!pin_writes);
    CHECK(!transport_stop(active,clock_us+100000));CHECK(!platform_assert_perst(active,clock_us+10000));
    CHECK(active->platform_perst_verified&&!(pin_regs[1]&3)&&irq_masked&&dbi[EldenMsiEnable/4]==0);
    EldenPcieTransportStatus snapshot={};CHECK(!transport_snapshot(active,&snapshot)&&!snapshot.ready&&snapshot.receiver_state==EldenMsiStopped);
    for(unsigned condition=0;condition<5;condition++){
        prepare();if(condition==0)active->platform_callback_returned=false;if(condition==1)active->runtime_returned=false;
        if(condition==2)active->runtime_consumer=active;if(condition==3)platform_config_error=-5;if(condition==4)active->runtime_thread=nullptr;
        before=calls;CHECK(platform_fence_run(active)!=0&&calls==before&&!pin_writes);
    }
    for(unsigned step=3;step<=count;step++){
        prepare();fail_at=calls+step;CHECK(platform_fence_run(active)!=0);CHECK(!active->platform_perst_verified&&!pin_writes);
    }
    prepare();cfg[0]=0xffffffff;CHECK(platform_fence_run(active)==-19&&(cfg[1]&7)==6&&!pin_writes);
    prepare();cfg[0x48/4]|=32u<<16;pending_until=clock_us+3000;
    CHECK(!platform_fence_run(active)&&clock_us>=pending_until&&active->platform_fence.transactions_sampled);
    prepare();cfg[0x48/4]|=32u<<16;pending_until=1;stuck_pending=true;
    CHECK(platform_fence_run(active)==-110&&active->platform_fence.master_off&&active->platform_fence.transactions_sampled&&!active->platform_fence.transactions_idle);
    active->runtime_quiesced=true;CHECK(platform_assert_perst(active,clock_us+10000)!=0&&!pin_writes);
    prepare();CHECK(!platform_fence_run(active));active->runtime_quiesced=true;cfg[1]|=4;
    CHECK(elden_pcie_msi_stop(&active->msi,clock_us+10000)==-71);CHECK(platform_assert_perst(active,clock_us+10000)!=0&&!pin_writes);
    prepare();CHECK(!platform_fence_run(active));active->runtime_quiesced=true;cfg[0x48/4]|=32u<<16;
    CHECK(platform_assert_perst(active,clock_us+10000)==-71&&!pin_writes);
    prepare();CHECK(!platform_fence_run(active));active->runtime_quiesced=true;fail_at=calls+4;
    CHECK(elden_pcie_msi_stop(&active->msi,clock_us+10000)!=0);CHECK(platform_assert_perst(active,clock_us+10000)!=0&&!pin_writes);
    prepare();dma_and_msi();pin_error=-5;CHECK(platform_assert_perst(active,clock_us+10000)==-5&&!active->platform_perst_verified);
    prepare();dma_and_msi();stuck_pin=true;CHECK(platform_assert_perst(active,clock_us+10000)==-110&&!active->platform_perst_verified);
    prepare();dma_and_msi();pin_regs[0]|=8;CHECK(platform_assert_perst(active,clock_us+10000)==-19&&!pin_writes);
    prepare();dma_and_msi();active->pins.initialized=false;CHECK(platform_assert_perst(active,clock_us+10000)==-16&&!pin_writes);
    prepare();dma_and_msi();CHECK(platform_assert_perst(active,clock_us)==-110&&!pin_writes);
    prepare();dma_and_msi();CHECK(platform_assert_perst(active,clock_us+500)==-110&&!active->platform_perst_verified);
    printf("%u platform fence scenarios / %u checks passed; actual config/MSI/PERST/native helpers, callback claims and MMIO modeled\\n",cases,checks);
}
'''
    (out/'Test.cpp').write_text(s,encoding='utf-8')
    flags=['-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(out),'-I'+str(d),'-I'+str(ROOT/'drivers/EldenSmmu')]
    commands=[['clang','-std=c11',*flags,'-c',str(d/(n+'.c')),'-o',str(out/(n+'.o'))] for n in ['Config','Msi','PlatformFence']]
    commands+=[['clang++','-std=c++17',*flags,str(out/'Test.cpp'),*map(str,[out/'Config.o',out/'Msi.o',out/'PlatformFence.o']),'-o',str(out/'test')],[str(out/'test')]]
    for name,cmd in zip(['config','msi','fence','link','run'],commands):
        r=subprocess.run(cmd,capture_output=True,timeout=90);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    files=[d/n for n in ['PlatformFence.c','PlatformFence.h','PlatformFenceNative.inc','Config.c','Config.h','Msi.c','Msi.h','Pins.h','TransportNativeRuntime.inc','TestTransport.cpp']]+[Path(__file__)]
    result={'passed':True,'result':r.stdout.decode().strip(),'asan_ubsan':True,'callback_and_mmio_modeled':True,'hardware':False,'source_inputs':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()

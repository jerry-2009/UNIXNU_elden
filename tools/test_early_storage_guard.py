"""Execute the transformed early arm/adoption/stall paths with the real WDT core."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenCpuActivation'))
from EarlyStorageSource import recovery,source
def function(text,signature):
    start=text.index(signature);brace=text.index('{',start);depth=1;end=brace+1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cxx',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    body=recovery().decode();start=function(body,'static void eldenStartSmpGuard(void)\n{');worker=function(body,'static void eldenSmpGuardWorker(void *,wait_result_t)\n{')
    core=(ROOT/'drivers/EldenCpuActivation/GunyahWatchdog.c').read_text()
    for name in ('status','stop','arm','pet'):
        signature='int elden_vdog_'+name+'(EldenVdog *s,'
        assert function(body,signature)==function(core,signature),'Embedded watchdog differs from tested core'
    worker=worker[:worker.index('  __atomic_store_n(&gEldenFramebufferReady')]+ '  admitted=true;\n}'
    stall=function(body,'static void eldenEarlyStorageGate(void){')
    stall=stall.replace('__asm__ volatile("msr daifset, #3\\n\\tisb":::"memory");','masked=true;').replace('__asm__ volatile("yield");','(void)0;')
    fixture=r'''
#include "GunyahWatchdog.h"
#include "GuardPolicy.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <stdexcept>
#include "GunyahWatchdog.c"
using wait_result_t=int;using thread_t=void*;enum{KERN_SUCCESS=0};
static unsigned mode,cpus,smp,self,hold,control,timeSets,enables,pets,threads;
static uint64_t nowMs,lastPet,readyAt;static uint32_t failOp;static bool route,threadFail,admitted,masked,dtr;static std::string logText;
static unsigned gEldenSmpCount,gEldenSmpHoldSeconds,gEldenVdogStarted,gEldenSmpOwned,gEldenSmpPanic,gEldenRpcState;
static unsigned gEldenEarlyMode,gEldenEarlyPrepared;static int gEldenEarlyError;static uint64_t gEldenEarlyArmedAt;
static EldenVdog gEldenVdog;static struct {unsigned state;int processor;}gEldenDeadline;
static struct {unsigned busy;}gEldenUsb;
static void eldenSmpGuardWorker(void*,wait_result_t);
static void eldenStartSmpGuard(void);
static uint64_t eldenDeadlineCounter(){return nowMs*19200;}
static unsigned eldenEarlyMode(){return mode==3||mode==4?mode:0;}
static bool PE_parse_boot_argn(const char*n,unsigned*v,size_t){*v=!strcmp(n,"cpus")?cpus:!strcmp(n,"sheng-smp")?smp:!strcmp(n,"armcpu-self-ipi")?self:!strcmp(n,"smp-hold")?hold:mode;return true;}
static bool elden_recovery_armed(){return route;}
static int current_processor(){return 1;}static int current_thread(){return 1;}static void thread_bind(int){}static void thread_block(void*){}static void*THREAD_CONTINUE_NULL;
static void thread_terminate(int){}static void thread_deallocate(thread_t){}static int ml_get_max_cpu_number(){return (int)cpus-1;}static int ml_get_boot_cpu_number(){return 0;}
static int kernel_thread_start(void(*fn)(void*,int),void*,thread_t*t){assert(fn==eldenSmpGuardWorker);threads++;*t=(void*)1;return threadFail?1:0;}
struct Reset:std::exception{bool watchdog;Reset(bool w):watchdog(w){}};
static void advance(unsigned ms){nowMs+=ms;if((control&1)&&nowMs-lastPet>=30000)throw Reset(true);}
static void IOSleep(unsigned ms){advance(ms);}static void IODelay(unsigned us){advance((us+999)/1000);}
static void eldenSdamLog(const char*s){logText+=s;}
static void eldenVdogTrialReport(const char*s,int rc){logText+=std::string(s)+":"+std::to_string(rc)+"\n";}
static bool eldenVdogTrialReady(){return route&&nowMs>=readyAt;}
static EldenVdogReply fakeCall(void*,uint32_t fn,uint32_t a,uint32_t b){
 if(fn==failOp)return {(uint64_t)-7,0,0,0};
 if(fn==ELDEN_VDOG_STATUS)return {0,control,nowMs-lastPet,0};
 if(fn==ELDEN_VDOG_TIME){assert(a==27000&&b==30000);timeSets++;return {};}
 if(fn==ELDEN_VDOG_CONTROL){assert(a==2||a==3);control=a==3?1:0;if(a==3)enables++;return {};}
 assert(fn==ELDEN_VDOG_PET&&a==0&&b==0);pets++;lastPet=nowMs;return {};
}
static EldenVdogReply eldenSmpSmc(void*p,uint32_t fn,uint32_t a,uint32_t b){if(fn==ELDEN_VDOG_CONTROL&&a==3)gEldenSmpOwned=1;auto r=fakeCall(p,fn,a,b);if(fn==ELDEN_VDOG_CONTROL&&a==2&&!r.a0)gEldenSmpOwned=0;return r;}
static void*eldenDwc(){return nullptr;}struct dwc3_snapshot{bool configured,dtr;};static void dwc3_snapshot(void*,struct dwc3_snapshot*s){s->configured=s->dtr=dtr;}static bool dwc3_ready(void*){return dtr;}
static void elden_usb_panic_drain(){advance(1);}static void eldenSdamResetNow(){throw Reset(false);}
@WORKER@
@START@
@STALL@
static void reset(unsigned m){mode=m;cpus=8;smp=self=1;hold=600;control=timeSets=enables=pets=threads=0;nowMs=lastPet=0;readyAt=10000;failOp=0;route=dtr=true;threadFail=admitted=masked=false;gEldenSmpCount=gEldenSmpHoldSeconds=gEldenVdogStarted=gEldenSmpOwned=gEldenSmpPanic=gEldenRpcState=gEldenEarlyMode=gEldenEarlyPrepared=0;gEldenEarlyError=0;gEldenEarlyArmedAt=0;gEldenVdog={};gEldenDeadline={1,1};gEldenUsb={};logText.clear();}
int main(){unsigned cases=0;
 reset(3);eldenStartSmpGuard();assert(timeSets==1&&enables==1&&pets==1&&threads==1&&gEldenEarlyPrepared);eldenSmpGuardWorker(nullptr,0);assert(admitted&&timeSets==1&&enables==1&&pets>=10&&logText.find("SMP_ADOPT:0")!=std::string::npos);cases++;
 reset(2);eldenStartSmpGuard();assert(!timeSets&&!enables&&threads==1&&!gEldenEarlyPrepared);eldenSmpGuardWorker(nullptr,0);assert(admitted&&enables==1&&pets==1&&logText.find("SMP_ARM:0")!=std::string::npos);cases++;
 reset(3);readyAt=200000;eldenStartSmpGuard();eldenSmpGuardWorker(nullptr,0);assert(!admitted&&nowMs==120000);try{advance(30000);assert(false);}catch(const Reset&r){assert(r.watchdog);}cases++;
 reset(3);eldenStartSmpGuard();gEldenSmpPanic=1;eldenSmpGuardWorker(nullptr,0);assert(!admitted&&pets==1);cases++;
 for(uint32_t op:{(uint32_t)ELDEN_VDOG_STATUS,(uint32_t)ELDEN_VDOG_TIME}){reset(3);failOp=op;try{eldenEarlyStorageGate();assert(false);}catch(const Reset&r){assert(!r.watchdog&&!gEldenEarlyPrepared&&!enables);}cases++;}
 reset(3);control=1;try{eldenEarlyStorageGate();assert(false);}catch(const Reset&r){assert(!r.watchdog&&!timeSets&&!enables);}cases++;
 reset(3);threadFail=true;try{eldenEarlyStorageGate();assert(false);}catch(const Reset&r){assert(!r.watchdog&&enables==1&&!gEldenEarlyPrepared);}cases++;
 for(bool host:{true,false}){reset(4);dtr=host;try{eldenEarlyStorageGate();assert(false);}catch(const Reset&r){assert(r.watchdog&&nowMs==30000&&pets==1&&threads==0&&masked);assert(logText.find(host?"STALL before-ufs":"STALL_UNOBSERVED")!=std::string::npos);assert(logText.find("STALL_FALLBACK")==std::string::npos);}cases++;}
 reset(3);eldenStartSmpGuard();failOp=ELDEN_VDOG_PET;eldenSmpGuardWorker(nullptr,0);assert(!admitted&&logText.find("EARLY_PET_FAILED")!=std::string::npos);cases++;
 printf("PASS %u early arm/adoption/stall cases\n",cases);
}
'''.replace('@WORKER@',worker).replace('@START@',start).replace('@STALL@',stall)
    src=out/'early.cpp';src.write_text(fixture);exe=out/'early'
    cmd=[a.cxx,'-std=c++17','-O1','-g','-fsanitize=address,undefined','-I',str(ROOT/'drivers/EldenCpuActivation'),str(src),'-o',str(exe)]
    if sys.platform.startswith('linux'):cmd[1:1]=['-fno-pie','-no-pie']
    for name,command in [('compile',cmd),('run',[str(exe)])]:
        r=subprocess.run(command,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    start_body=function(source().decode(),'bool NativeUfs::start (IOService *provider)')
    assert start_body.index('eldenArmSdamRecovery()')<start_body.index('eldenEarlyStorageGate()')<start_body.index('hostBringUp (')
    report={'passed':True,'result':r.stdout.decode().strip(),'actual_transformed_paths':True,'actual_wdt_core':True,'asm_and_kernel_modeled':True,'asan_ubsan':True,'source_sha256':hashlib.sha256(source()).hexdigest(),'recovery_sha256':hashlib.sha256(recovery()).hexdigest(),'hardware':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()

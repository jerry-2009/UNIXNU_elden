"""Run the actual PD observation predicate and brightness wait/abort functions."""
from pathlib import Path
import argparse,json,subprocess,sys,hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'drivers/EldenBacklight'),str(ROOT/'drivers/EldenPmicGlink')]
from PdStartupSource import client
from PdPowerSource import source

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cxx',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    body=source().decode();start=body.index('static int hold(Context *c,');end=body.index('static void run(unsigned mode){',start);actual=body[start:end]
    getter_name='extern "C" unsigned elden_pd_power_observation(void){'
    getter=client().decode().split(getter_name,1)[1]
    getter='static unsigned tested_pd_power_observation(void){'+getter
    fixture=r'''
#include "PdCompletion.h"
#include <cassert>
#include <cstdio>
#include <cstdarg>
#include <cstring>
struct Chip {unsigned level=1597,writes=0;};
struct Context {unsigned original=1597;Chip chip;};
static bool pdObservationActive,stopped;
static unsigned restoreConfirmed=1,holds,lowers,restores;
static unsigned fixedState=EldenPdReady;static int finishError,restoreError;
static uint64_t clockUs,readyAt,loseAt;
static volatile unsigned bootstrapStop,linkUp,linkEpoch;
static volatile uint64_t pdObservation;
static uint64_t mach_absolute_time(){return clockUs;}
static uint64_t milliseconds(uint64_t value){return value/1000;}
@GETTER@
static unsigned observation(){if(loseAt&&clockUs>=loseAt)return EldenPdExpired;if(clockUs<readyAt)return EldenPdPending;return fixedState;}
static unsigned (*elden_pd_power_observation)()=observation;
static uint64_t now_us(void*){return clockUs;}
static bool stopping(){return stopped;}
static bool sleepChecked(unsigned ms){clockUs+=(uint64_t)ms*1000;return !stopped;}
static unsigned remaining(){return 850-(unsigned)(clockUs/1000000);}
static unsigned (*elden_recovery_deadline_remaining)()=remaining;
static int elden_aw99706_check_health(Chip*){return 0;}
static int applyLevel(Context*c,unsigned value){assert(value==c->original/2);c->chip.level=value;c->chip.writes++;lowers++;return 0;}
static int restoreOriginal(Context*c){restores++;restoreConfirmed=!restoreError;if(!restoreError)c->chip.level=c->original;return restoreError;}
static void report(const char*fmt,...){va_list a;va_start(a,fmt);if(strstr(fmt,"load-phase="))holds++;if(strstr(fmt,"power-finished="))finishError=va_arg(a,int);va_end(a);}
@ACTUAL@
static void reset(){pdObservationActive=stopped=false;restoreConfirmed=1;holds=lowers=restores=0;finishError=restoreError=0;clockUs=readyAt=loseAt=0;fixedState=EldenPdReady;elden_pd_power_observation=observation;}
int main(){
 unsigned cases=0;clockUs=100000;linkUp=1;linkEpoch=17;pdObservation=elden_pd_observation_pack(EldenPdReady,17,100);
 assert(tested_pd_power_observation()==EldenPdReady);cases++;
 bootstrapStop=1;assert(tested_pd_power_observation()==EldenPdFailed);bootstrapStop=0;cases++;
 linkUp=0;assert(tested_pd_power_observation()==EldenPdUnavailable);linkUp=1;cases++;
 linkEpoch=18;assert(tested_pd_power_observation()==EldenPdUnavailable);linkEpoch=17;cases++;
 clockUs=3101000;assert(tested_pd_power_observation()==EldenPdExpired);cases++;
 EldenPdBootstrap s={};s.mode=2;s.phase=EldenPdBootDone;s.restored=true;s.epoch=7;
 EldenPdBootInput in={};in.epoch=7;in.cycle=20;in.link_up=in.qualified=in.raw_fresh=in.high_voltage=in.icl_owned=true;in.icl_applied=in.icl_observed=500000;in.pulse=EldenPulseReady;
 assert(elden_pd_completion_state(&s,&in)==EldenPdReady);cases++;
 for(unsigned n=0;n<17;n++){
  auto t=in;auto b=s;
  if(n==0)t.epoch=0;else if(n==1)t.epoch++;else if(n==2)t.cycle=0;else if(n==3)t.link_up=false;else if(n==4)t.qualified=false;
  else if(n==5)t.raw_fresh=false;else if(n==6)t.high_voltage=false;else if(n==7)t.icl_owned=false;else if(n==8)t.icl_pending=true;
  else if(n==9)t.icl_applied=100000;else if(n==10)t.icl_observed=0;else if(n==11)t.pulse=EldenPulseHigh;else if(n==12)t.icl_quarantined=true;
  else if(n==13)t.stop=true;else if(n==14)b.restored=false;else if(n==15)b.phase=EldenPdBootRestore;else b.error=EldenPdBootInterrupted;
  assert(elden_pd_completion_state(&b,&t)!=EldenPdReady);cases++;
 }
 in.pulse=EldenPulseRestored;assert(elden_pd_completion_state(&s,&in)==EldenPdReady);s.mode=1;assert(elden_pd_completion_state(&s,&in)==EldenPdDisabled);cases++;
 uint64_t stamp=elden_pd_observation_pack(EldenPdReady,7,100);
 assert(elden_pd_observation_read(stamp,7,3100)==EldenPdReady);assert(elden_pd_observation_read(stamp,7,3101)==EldenPdExpired);
 assert(elden_pd_observation_read(stamp,8,100)==EldenPdUnavailable);assert(!elden_pd_observation_pack(EldenPdReady,0x20000000,100));
 stamp=elden_pd_observation_pack(EldenPdReady,7,0xfffffff0ULL);assert(elden_pd_observation_read(stamp,7,0x100000010ULL)==EldenPdReady);
 assert(elden_pd_observation_read(stamp,7,0x100001000ULL)==EldenPdExpired);cases++;
 Context c;reset();readyAt=200000;powerTrial(&c);assert(clockUs>=165200000&&clockUs<166000000&&holds==4&&lowers==1&&restores==1&&c.chip.level==1597&&!pdObservationActive&&!finishError);cases++;
 for(unsigned state=EldenPdFailed;state<=EldenPdDisabled;state++){reset();c={};fixedState=state;powerTrial(&c);assert(!holds&&!lowers&&!restores&&!pdObservationActive);cases++;}
 reset();c={};fixedState=EldenPdPending;powerTrial(&c);assert(clockUs==240000000&&!holds&&!lowers);cases++;
 reset();c={};elden_pd_power_observation=nullptr;powerTrial(&c);assert(!holds&&!lowers);cases++;
 for(unsigned seconds: {40u,90u,140u}){reset();c={};loseAt=(uint64_t)seconds*1000000;powerTrial(&c);assert(finishError==-8&&restores==1&&c.chip.level==1597&&!pdObservationActive);assert(lowers==(seconds>=90?1u:0u));cases++;}
 reset();c={};restoreError=-5;powerTrial(&c);assert(finishError==-5&&!restoreConfirmed&&c.chip.level==798&&!pdObservationActive);cases++;
 printf("PASS %u PD observation/wait/cancellation scenarios\n",cases);
}
'''.replace('@ACTUAL@',actual).replace('@GETTER@',getter).replace('#include <cstring>','#include <cstring>\n#include <initializer_list>')
    src=out/'pd-power.cpp';src.write_text(fixture,encoding='utf-8');exe=out/'pd-power'
    cmd=[a.cxx,'-std=c++17','-O1','-g','-fsanitize=address,undefined','-I',str(ROOT/'drivers/EldenPmicGlink'),'-I',str(ROOT/'drivers/EldenUsbThermal'),str(src),'-o',str(exe)]
    r=subprocess.run(cmd,capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    r=subprocess.run([str(exe)],capture_output=True);(out/'run.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    report={'passed':True,'actual_backlight_functions':True,'actual_getter':True,'asan_ubsan':True,'result':r.stdout.decode().strip(),'client_sha256':hashlib.sha256(client()).hexdigest(),'backlight_sha256':hashlib.sha256(source()).hexdigest(),'hardware_tested':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()

"""Exercise the actual runtime/stop/window code with the real governor and fake kernel/FW."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenCpuPower'))
from GovernorSource import policy
from RuntimeSource import source,recovery,RECOVERY
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cxx',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);(out/'EldenCpuFreqPolicy.h').write_bytes(policy())
    fixture=(ROOT/'drivers/EldenCpuPower/TestGovernor.cpp').read_text(encoding='utf-8').split('int main(){',1)[0]
    fixture=fixture.replace('#include "GovernorControl.h"','#include "GovernorControl.h"\n#include "CpuLoad.h"\n#include <string>\n#include <cstdarg>\nstatic elden_cpufreq::Control governorControl;')
    fixture=fixture.replace('elden_cpufreq::Control control={};','elden_cpufreq::Control &control;').replace('Firmware(){','Firmware():control(governorControl){')
    for name in ('read','write','ring','pause'):
        fixture=re.sub(r'\b'+name+r'\b','firm_'+name,fixture)
    actual=(ROOT/'drivers/EldenCpuPower/Runtime.inc').read_text(encoding='utf-8')
    actual=actual.replace('static elden_cpufreq::Control governorControl;','')
    stop=source().decode().split('extern "C" int elden_cpu_governor_request_stop(void){',1)[1]
    extra=r'''
static Firmware *fake;static uint32_t sm8750_cpucp_owner,hz_tick_interval=192000,native_touch_seq;
static unsigned unmaps,stopAt,epochAt,badSampleAt;static bool pdReady,chargeReady,temperatureReady,mapBad;static int temperature;static std::string logText;
static volatile unsigned &stopFlag();
static void IOSleep(unsigned ms){fake->advance(ms);if(stopAt&&fake->ticks/19200>=stopAt)__atomic_store_n(&stopFlag(),1u,__ATOMIC_RELEASE);if(fake->ticks/19200>=45000)native_touch_seq=2;}
static uint64_t counter(void*){return fake->ticks;}static uint64_t counterFrequency(){return 19200000;}
static bool ml_at_interrupt_context(){return fake->irq;}
static bool elden_recovery_rpc_ready(){return true;}static unsigned elden_recovery_deadline_remaining(){return 900-(unsigned)(fake->ticks/19200000);}
static bool powerReady(){return pdReady;}static unsigned elden_charge_policy_ready(){return chargeReady;}
static bool elden_battery_temperature_get(int*t,uint32_t*e,uint32_t*c){*t=temperature;*e=epochAt&&fake->ticks/19200>=epochAt?2:1;*c=5;return temperatureReady;}
struct Window{uintptr_t address;};static Window tx,shared;
enum {ELDEN_CPUCP_TX_BASE=1,ELDEN_CPUCP_TX_BYTES=1,ELDEN_CPUCP_SCMI_BASE=2,ELDEN_CPUCP_SCMI_BYTES=1};
static bool map(Window&w,uint64_t,size_t){w.address=mapBad?0:1;return w.address;}
static void unmap(Window&w){w.address=0;++unmaps;}
static uint32_t read(void*,uint32_t o){return firm_read(fake,o);}static void write(void*,uint32_t o,uint32_t v){firm_write(fake,o,v);}
static void ring(void*,uint32_t v){firm_ring(fake,v);}static void pause(void*,uint64_t v){firm_pause(fake,v);}
static void report(const char*fmt,...){char b[700];va_list a;va_start(a,fmt);vsnprintf(b,sizeof(b),fmt,a);va_end(a);logText+=b;}
static bool sampleLoads(EldenCpuTicks out[8]){
 if(badSampleAt&&fake->ticks/19200>=badSampleAt)return false;
 for(unsigned c=0;c<8;++c){uint32_t total=(uint32_t)(fake->ticks/hz_tick_interval);out[c]={true,{total/4,0,total-total/4,0},fake->ticks};}
 return true;
}
@RUNTIME@
static volatile unsigned &stopFlag(){return governorStop;}
extern "C" int elden_cpu_governor_request_stop(void){@STOP@
static void reset(){delete fake;governorControl={};fake=new Firmware;sm8750_cpucp_owner=governorRun=governorStop=unmaps=native_touch_seq=stopAt=epochAt=badSampleAt=0;temperature=3000;pdReady=chargeReady=temperatureReady=true;mapBad=false;tx=shared={};logText.clear();}
int main(){unsigned n=0;
 reset();governorWorker();CHECK(governorRun==2&&!sm8750_cpucp_owner&&governorControl.windows>100&&governorControl.confirmations>0&&governorControl.restoreConfirmed==1);CHECK(fake->current[0]==8&&fake->current[1]==0&&unmaps==2);CHECK(elden_cpu_governor_request_stop()==1);++n;
 for(unsigned k=0;k<5;++k){reset();if(k==0)pdReady=false;if(k==1)chargeReady=false;if(k==2)temperatureReady=false;if(k==3)temperature=4500;if(k==4)governorStop=1;governorWorker();CHECK(governorRun==2&&fake->rings==0&&!sm8750_cpucp_owner);++n;}
 reset();sm8750_cpucp_owner=123;governorWorker();CHECK(fake->rings==0&&sm8750_cpucp_owner==123&&governorRun==2);++n;
 reset();mapBad=true;governorWorker();CHECK(fake->rings==0&&!sm8750_cpucp_owner&&governorRun==2);++n;
 for(unsigned stopMs:{10000u,31000u,60000u}){reset();stopAt=stopMs;governorWorker();CHECK(governorRun==2&&!sm8750_cpucp_owner&&fake->current[0]==8);if(stopMs==10000)CHECK(fake->rings==0);else CHECK(governorControl.restoreConfirmed==1);++n;}
 reset();epochAt=60000;governorWorker();CHECK(governorRun==2&&governorControl.failure==elden_cpufreq::ReadinessLost&&fake->current[0]==8);++n;
 reset();badSampleAt=60000;governorWorker();CHECK(governorRun==2&&governorControl.failure==elden_cpufreq::InvalidWindow&&fake->current[0]==8);++n;
 reset();fake->silentSet=1;governorWorker();CHECK(governorRun==3&&sm8750_cpucp_owner&&unmaps==0&&fake->sets.size()==1);unsigned calls=fake->rings;CHECK(elden_cpu_governor_request_stop()==0&&fake->rings==calls);++n;
 reset();CHECK(elden_cpu_governor_request_stop()==1);governorWorker();CHECK(governorRun==2&&!fake->rings);++n;
 reset();governorRun=1;uint64_t before=fake->ticks;CHECK(elden_cpu_governor_request_stop()==0&&fake->ticks-before==5000ull*19200);CHECK(!fake->rings);++n;
 delete fake;fake=nullptr;printf("PASS %u runtime cases / %u checks\n",n,checks);
}
'''.replace('@RUNTIME@',actual).replace('@STOP@',stop)
    src=out/'runtime.cpp';src.write_text(fixture+extra,encoding='utf-8');exe=out/'runtime'
    cmd=[a.cxx,'-std=c++17','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(out),'-I',str(ROOT/'drivers/EldenCpuPower'),'-I',str(ROOT/'profiles/v91/sources/power'),str(src),'-o',str(exe)]
    if sys.platform.startswith('linux'):cmd[1:1]=['-fno-pie','-no-pie']
    for label,command in [('compile',cmd),('run',[str(exe)])]:
        result=subprocess.run(command,capture_output=True);(out/(label+'.log')).write_bytes(result.stdout+result.stderr);result.check_returncode()
    old=RECOVERY.read_bytes();new=recovery();start=new.index(b'  if(elden_cpu_governor_request_stop){');end=new.index(b'  if(elden_wcn_request_stop){',start)
    removed=new[:start]+new[end:];removed=removed.replace(b'extern "C" int elden_cpu_governor_request_stop(void) __attribute__((weak_import));\n',b'')
    assert removed==old
    assert new.decode().index('int stopped=elden_cpu_governor_request_stop();')<new.decode().index('int stopped=elden_wcn_request_stop();')
    assert b'for(unsigned wait=0;wait<500;' in source()
    files=['drivers/EldenCpuPower/'+f for f in ('Runtime.inc','RuntimeSource.py','GovernorControl.h','GovernorSource.py','TestGovernor.cpp','Survey.inc','SurveySource.py','CpuLoad.h','upstream/CpuFreqGovernor.h','upstream/source.json','upstream/LICENSE')]+['tools/test_cpu_governor_runtime.py','profiles/v97-wcn/EldenSdamRecovery.inc']
    files+=['profiles/v91/sources/power/'+f for f in ('EldenScmiPerf.h','CpuPerfAccess.h','CpuPerfSurvey.cpp')]
    r={'passed':True,'actual_runtime':True,'actual_stop_callback':True,'actual_controller_scmi':True,'asan_ubsan':True,'result':result.stdout.decode().strip(),'source_sha256':hashlib.sha256(source()).hexdigest(),'policy_sha256':hashlib.sha256(policy()).hexdigest(),'recovery_sha256':hashlib.sha256(new).hexdigest(),'source_inputs':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files},'hardware':False,'native_compiled':False,'limits':'Kernel readiness/load/MMIO are modeled; no device, no real concurrency or scheduler budget acceptance.'}
    (out/'result.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in r.items() if k!='source_inputs'}))
if __name__=='__main__':main()

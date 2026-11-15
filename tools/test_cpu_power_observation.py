"""Execute the actual combined observer with deterministic kernel/SCMI fault injection."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys,tomllib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenCpuPower'))
from SurveySource import source

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cxx',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--parser-source',type=Path);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    code=source().decode();begin=code.index('static bool powerReady(void)');end=code.index('static void worker(',begin)
    fixture=r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <cstdarg>
#include <string>
#include "CpuLoad.h"
using processor_t=void*;using host_t=void*;using processor_info_t=int*;using mach_msg_type_number_t=unsigned;
struct processor_basic_info_data_t {int running,slot_num;};
struct processor_cpu_load_info_data_t {uint32_t cpu_ticks[4];};
enum {PROCESSOR_BASIC_INFO=1,PROCESSOR_CPU_LOAD_INFO=2,PROCESSOR_BASIC_INFO_COUNT=2,PROCESSOR_CPU_LOAD_INFO_COUNT=4,KERN_SUCCESS=0,EldenPdReady=2};
static uint64_t ms;static int offline=-1,infoError=-1,countError=-1,resetCpu=-1,denied=-1,transportError=-1;
static bool ready=true,stopAfter=false,probeError=false,mapError=false;static unsigned owner,levelGets[2],unmaps,validLoads;
static uint64_t loseAt;static std::string logs;static int native_owner_data_status=0,elden_init_exec_accepted=1;
static uint32_t &sm8750_cpucp_owner=owner;static uint32_t hz_tick_interval=192000;
static bool malformed_access;static bool elden_recovery_armed(){return true;}
static unsigned elden_pd_power_observation(){return ready&&(!loseAt||ms<loseAt)?2:5;}
static uint64_t mach_absolute_time(){return ms*19200;}static uint64_t counterFrequency(){return 19200000;}
static void IOSleep(unsigned m){ms+=m;}
static processor_t cpu_to_processor(int c){return (void*)(uintptr_t)(c+1);}
static int processor_info(processor_t p,int flavor,host_t*,processor_info_t out,unsigned*count){
 int c=(int)(uintptr_t)p-1;if(c==infoError)return 5;
 if(flavor==PROCESSOR_BASIC_INFO){auto b=(processor_basic_info_data_t*)out;b->running=c!=offline;b->slot_num=c;*count=2;}
 else {auto b=(processor_cpu_load_info_data_t*)out;uint32_t total=(uint32_t)(ms/10);b->cpu_ticks[0]=total/5;b->cpu_ticks[1]=0;b->cpu_ticks[2]=total-b->cpu_ticks[0];b->cpu_ticks[3]=0;*count=c==countError?3:4;if(c==resetCpu&&ms>32000)b->cpu_ticks[2]=0;}
 return 0;
}
static void report(const char *fmt,...){char b[1024];va_list a;va_start(a,fmt);vsnprintf(b,sizeof(b),fmt,a);va_end(a);logs+=b;if(strstr(b,"ELDEN_CPU_LOAD")&&strstr(b," valid=1 "))validLoads++;}
struct Window{uintptr_t address;};static Window tx,shared;
enum {ELDEN_CPUCP_TX_BASE=1,ELDEN_CPUCP_TX_BYTES=1,ELDEN_CPUCP_SCMI_BASE=2,ELDEN_CPUCP_SCMI_BYTES=1};
static bool map(Window&w,uint64_t,size_t){w.address=mapError?0:1;return w.address;}
static void unmap(Window&w){w.address=0;unmaps++;}
static uint32_t channelStatus=1;static uint32_t read(void*,uint32_t){return channelStatus;}
static void write(void*,uint32_t,uint32_t){assert(false);}static void ring(void*,uint32_t){assert(false);}
static uint64_t counter(void*){return ms*19200;}static void pause(void*,uint64_t){}static bool allowMessage(void*,uint32_t p,uint32_t m){return p==0x13&&(m==0||m==1||m==3||m==4||m==6||m==8);}
namespace scmi {
enum {kStatus=6,kHeader=24,kChannelStatus=4,kChannelFree=1};
struct Result {int error,status;};static bool ok(Result r){return !r.error&&!r.status;}
struct Level {uint32_t value,khz,latencyUs;};struct Domain {char name[6];uint32_t flags,count;Level levels[1];};
struct Io {void*ctx;uint32_t(*r)(void*,uint32_t);void(*w)(void*,uint32_t,uint32_t);void(*ring)(void*,uint32_t);uint64_t(*now)(void*);void(*pause)(void*,uint64_t);void*unused;uint64_t hz;unsigned timeout;bool(*allow)(void*,uint32_t,uint32_t);};
struct Perf {struct {Io io;unsigned sequence;uint64_t transfers;}channel;unsigned domains,baseVersion,perfVersion;Domain domain[2];};
static unsigned headerToken(uint32_t){return 0;}
static Result probe(Perf*p){p->channel.transfers++;p->domains=2;p->baseVersion=0x20000;p->perfVersion=0x40000;for(unsigned d=0;d<2;d++){p->domain[d].count=1;strcpy(p->domain[d].name,d?"NCC1":"NCC0");p->domain[d].levels[0]={0,1996800,30};}return {probeError?1:0,0};}
static Result levelGet(Perf*p,unsigned d,uint32_t*i,uint32_t*r){p->channel.transfers++;levelGets[d]++;assert(p->channel.io.allow(nullptr,0x13,8));if((int)d==transportError){channelStatus=0;return {4,0};}if((int)d==denied)return {6,-2};*i=*r=0;return {};}
}
static scmi::Perf perf;static bool show(const char*,scmi::Result r){return scmi::ok(r);}
@ACTUAL@
static void reset(){ms=loseAt=0;offline=infoError=countError=resetCpu=denied=transportError=-1;ready=true;probeError=mapError=false;owner=levelGets[0]=levelGets[1]=unmaps=validLoads=0;channelStatus=1;logs.clear();tx=shared={};perf={};}
int main(){unsigned cases=0;
 EldenCpuTicks a={true,{10,20,30,0},0},b={true,{20,40,100,0},19200000};auto d=elden_cpu_load(a,b,192000);assert(d.valid&&d.busy_pm==300&&d.total==100);cases++;
 a.ticks[0]=0xfffffff0;b=a;b.at=19200000;b.ticks[0]=0x54;d=elden_cpu_load(a,b,192000);assert(d.valid&&d.busy_pm==1000);cases++;
 a={true,{1000,0,0,0},1};b={true,{10,0,0,0},19200001};assert(!elden_cpu_load(a,b,192000).valid);cases++;
 for(unsigned i=0;i<6;i++){a={true,{0,0,0,0},1};b={true,{0,0,100,0},19200001};uint64_t tick=192000;if(i==0)a.valid=false;if(i==1)b.valid=false;if(i==2)b.at=1;if(i==3)tick=0;if(i==4)b.ticks[2]=104;if(i==5)b.at=192001;assert(!elden_cpu_load(a,b,tick).valid);cases++;}
 reset();powerObservation();assert(logs.find("end ok=1 complete=1 intervals=8")!=std::string::npos&&levelGets[0]==9&&levelGets[1]==9&&validLoads==64&&owner==0&&unmaps==2);cases++;
 for(unsigned d=0;d<2;d++){reset();denied=d;powerObservation();assert(levelGets[d]==1&&levelGets[1-d]==9&&validLoads==64&&logs.find("end ok=1 complete=0")!=std::string::npos&&!owner);cases++;}
 reset();transportError=0;powerObservation();assert(levelGets[0]==1&&!levelGets[1]&&owner&&unmaps==0&&logs.find("end ok=0 complete=0")!=std::string::npos);cases++;
 for(unsigned kind=0;kind<4;kind++){reset();if(kind==0)ready=false;if(kind==1)offline=7;if(kind==2)infoError=0;if(kind==3)countError=2;powerObservation();assert(!perf.channel.transfers&&!owner&&!unmaps);cases++;}
 for(uint64_t lost:{15000ULL,33000ULL}){reset();loseAt=lost;powerObservation();assert(logs.find("complete=1")==std::string::npos&&!owner);if(lost==15000)assert(!perf.channel.transfers);cases++;}
 reset();owner=123;powerObservation();assert(!perf.channel.transfers&&owner==123&&!unmaps);cases++;
 reset();mapError=true;powerObservation();assert(!perf.channel.transfers&&!owner);cases++;
 reset();probeError=true;powerObservation();assert(!levelGets[0]&&!levelGets[1]&&!owner);cases++;
 reset();resetCpu=5;powerObservation();assert(logs.find("end ok=1 complete=0")!=std::string::npos&&validLoads<64&&!owner);cases++;
 printf("PASS %u actual observer/load/failure cases\n",cases);
}
'''.replace('@ACTUAL@',code[begin:end])
    src=out/'observer.cpp';src.write_text(fixture,encoding='utf-8');exe=out/'observer'
    command=[a.cxx,'-std=c++17','-O1','-g','-fsanitize=address,undefined','-I',str(ROOT/'drivers/EldenCpuPower'),str(src),'-o',str(exe)]
    for label,cmd in [('compile',command),('run',[str(exe)])]:
        r=subprocess.run(cmd,capture_output=True);(out/(label+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    result={'passed':True,'result':r.stdout.decode().strip(),'asan_ubsan':True,'actual_observer':True,'source_sha256':hashlib.sha256(source()).hexdigest(),'hardware':False,'limits':'Mock kernel counters and SCMI results; no real CPU load, transport or power acceptance.'}
    from bt_runtime_boot import menu
    from battery_boot import arguments
    before=tomllib.loads(menu({'profile':'pd-gui'}));after=tomllib.loads(menu({'profile':'cpu-power-observation'}))
    old=arguments(before['entry'][0]['args']);new=arguments(after['entry'][0]['args'])
    assert new.pop('ecp')=='2' and int(new.pop('debug'),0)==int(old.pop('debug'),0) and new==old
    assert before['entry'][1:]==after['entry'][1:] and before['boot']==after['boot']
    actual=after['entry'][0]['args'].replace('@SESSION@','0'*16);assert len(actual.encode())==1023
    if a.parser_source:
        from test_battery_boot import actual_parser
        actual_parser(a.parser_source,out/'parser',a.cxx,[(actual,{'ecp':2,'debug':334,'security-mode-change-enable':1,'amfi_get_out_of_my_way':1})])
        result['actual_bootarg_parser']=True
    result['menu_bytes']=len(actual.encode())
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()

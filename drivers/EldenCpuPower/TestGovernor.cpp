/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "GovernorControl.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
static unsigned checks,cases;
#define CHECK(v) do{++checks;if(!(v)){fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#v);abort();}}while(0)
static const uint32_t levels[2][16]={
 {384000,556800,748800,960000,1152000,1363200,1555200,1785600,1996800,2227200,2400000,2745600,2918400,3072000,3321600,3532800},
 {1017600,1209600,1401600,1689600,1958400,2246400,2438400,2649600,2841600,3072000,3283200,3513600,3801600,4089600,4204800,4320000}};
struct Set {unsigned domain,level;bool restore;uint64_t at;};
struct Firmware {
 elden_cpufreq::Control control={};uint32_t words[128]={};uint64_t ticks=1;
 unsigned reads=0,writes=0,rings=0,current[2]={8,0},target[2]={8,0};uint64_t due[2]={};
 unsigned delayMs=40,rejectSet=0,silentSet=0;int rejectStatus=-3;bool rejectGet=false,badGet=false,noCapability=false,badTable=false,duplicateValue=false;
 unsigned rateUs=0;bool irq=false;std::vector<Set> sets;
 Firmware(){words[scmi::kChannelStatus/4]=1;}
 void advance(unsigned ms){ticks+=(uint64_t)ms*19200;for(unsigned d=0;d<2;++d)if(due[d]&&ticks>=due[d]){current[d]=target[d];due[d]=0;}}
};
static uint32_t read(void*p,uint32_t off){auto*f=(Firmware*)p;CHECK(off<512&&!(off&3));++f->reads;return f->words[off/4];}
static void write(void*p,uint32_t off,uint32_t value){auto*f=(Firmware*)p;CHECK(off<512&&!(off&3));++f->writes;f->words[off/4]=value;}
static uint64_t clockNow(void*p){return ((Firmware*)p)->ticks;}
static void pause(void*p,uint64_t){((Firmware*)p)->advance(1);}
static bool threadAllowed(void*p){return !((Firmware*)p)->irq;}
static bool messageAllowed(void*p,uint32_t protocol,uint32_t message){return elden_cpufreq::allowed(&((Firmware*)p)->control,protocol,message);}
static void ring(void*p,uint32_t){
 auto*f=(Firmware*)p;++f->rings;uint32_t h=f->words[scmi::kHeader/4],protocol=scmi::headerProtocol(h),message=scmi::headerMessage(h);
 CHECK(messageAllowed(p,protocol,message));CHECK(message!=scmi::kLimitsSet);
 unsigned d=f->words[scmi::kPayload/4],argument=f->words[scmi::kPayload/4+1];
 uint32_t*r=f->words+scmi::kPayload/4+1;memset(r,0,81*4);unsigned count=0;int status=0;
 if(message==scmi::kVersion){r[0]=protocol==scmi::kBase?0x20000:0x40000;count=1;}
 else if(message==scmi::kAttributes){r[0]=2;count=4;}
 else if(message==scmi::kDomainAttributes){CHECK(d<2);r[0]=(f->noCapability?0:scmi::kCanSetLevel)|scmi::kLevelIndexing;r[1]=f->rateUs;r[2]=d?4089600:3532800;r[3]=16;memcpy(r+4,d?"NCC1":"NCC0",4);count=8;}
 else if(message==scmi::kDescribeLevels){CHECK(d<2&&argument==0);r[0]=16;for(unsigned i=0;i<16;++i){r[1+5*i]=i+1;r[3+5*i]=30;r[4+5*i]=f->badTable&&i==1?levels[d][0]:levels[d][i];r[5+5*i]=f->duplicateValue&&i==1?0:i;}count=81;}
 else if(message==scmi::kLevelGet){CHECK(d<2);if(f->rejectGet&&!f->sets.empty())status=-2;r[0]=f->badGet&&!f->sets.empty()?999:f->current[d];count=1;}
 else if(message==scmi::kLevelSet){
  CHECK(d<2&&argument<16);bool restoring=f->control.phase==elden_cpufreq::Restoring;
  CHECK(restoring?argument==f->control.original[d]:argument<=f->control.ceiling[d]);
  f->sets.push_back({d,argument,restoring,f->ticks});
  if(f->sets.size()==f->silentSet)return;
  if(f->sets.size()==f->rejectSet)status=f->rejectStatus;
  else {f->target[d]=argument;f->due[d]=f->ticks+(uint64_t)f->delayMs*19200;}
 }else CHECK(false);
 f->words[scmi::kPayload/4]=(uint32_t)status;f->words[scmi::kLength/4]=8+4*count;f->words[scmi::kChannelStatus/4]=1;
}
static scmi::Io io(Firmware&f){return {&f,read,write,ring,clockNow,pause,threadAllowed,19200000,30,messageAllowed};}
static bool start(Firmware&f,bool boot=true){return elden_cpufreq::initialize(&f.control,io(f),{{3532800,4089600},boot},true);}
static elden_cpufreq::Input sample(unsigned busy=0,unsigned touches=0){elden_cpufreq::Input in={};in.ready=true;in.touches=touches;for(unsigned c=0;c<8;++c)in.cpu[c]={c<6?0u:1u,(uint64_t)384000*busy/1000,384000};return in;}
static void step(Firmware&f,elden_cpufreq::Input in,unsigned ms=20){f.advance(ms);elden_cpufreq::step(&f.control,in);}
static void stop(Firmware&f){auto in=sample();in.stop=true;for(unsigned n=0;n<180&&!elden_cpufreq::terminal(&f.control);++n)step(f,in);CHECK(elden_cpufreq::terminal(&f.control));}
static void firstSet(Firmware&f){for(unsigned n=0;n<80&&f.sets.empty();++n)step(f,sample());CHECK(!f.sets.empty());}
static void quiet(Firmware&f,unsigned n=40){for(unsigned i=0;i<n&&!elden_cpufreq::terminal(&f.control);++i)step(f,sample());}

int main(){
 using namespace elden_cpufreq;
 {Firmware f;auto x=io(f);CHECK(!initialize(&f.control,x,{{3532800,4089600},true},false));CHECK(f.rings==0);++cases;}
 for(unsigned kind=0;kind<3;++kind){Firmware f;auto x=io(f);if(kind==0)x.allowed=nullptr;if(kind==1)x.allowMessage=nullptr;if(kind==2)x.now=nullptr;CHECK(!initialize(&f.control,x,{{3532800,4089600},true},true));CHECK(!f.rings&&!f.writes&&!f.reads);++cases;}
 {Firmware f;CHECK(start(f));unsigned n=f.rings;CHECK(!start(f)&&f.rings==n&&f.control.phase==Running);stop(f);CHECK(f.control.phase==Stopped);++cases;}
 {Firmware f;CHECK(start(f));CHECK(f.control.ceiling[0]==8&&f.control.ceiling[1]==0&&f.sets.empty());unsigned r=f.reads,w=f.writes,n=f.rings;CHECK(!scmi::ok(scmi::levelSet(&f.control.perf,0,0)));CHECK(f.reads==r&&f.writes==w&&f.rings==n);f.control.permitSet=true;uint32_t p[3]={};CHECK(!scmi::ok(scmi::transfer(&f.control.perf.channel,scmi::kPerf,scmi::kLimitsSet,p,3,nullptr,0,nullptr)));CHECK(f.rings==n);f.control.permitSet=false;stop(f);CHECK(f.control.phase==Stopped&&f.sets.empty());++cases;}
 {Firmware f;CHECK(start(f));firstSet(f);CHECK(f.control.phase==Confirming&&f.control.confirmations==0&&f.current[0]==8);step(f,sample());CHECK(f.control.confirmations==0);step(f,sample());CHECK(f.control.confirmations==1&&f.current[0]<8);quiet(f);CHECK(f.current[0]==3&&f.current[1]==0);stop(f);CHECK(f.current[0]==8&&f.current[1]==0&&f.control.phase==Stopped&&f.control.restoreConfirmed==1);++cases;}
 {Firmware f;CHECK(start(f));quiet(f);unsigned low=f.current[0];CHECK(low==3);for(unsigned n=0;n<20;++n)step(f,sample(1000,1));CHECK(f.current[0]==8);for(const auto&s:f.sets)CHECK(s.domain==0&&s.level<=8);stop(f);CHECK(f.control.phase==Stopped);++cases;}
 {Firmware f;CHECK(start(f,false));quiet(f);for(unsigned n=0;n<30;++n)step(f,sample(1000,1));CHECK(f.current[0]==15&&f.current[1]==13);stop(f);CHECK(f.current[0]==8&&f.current[1]==0&&f.control.restoreConfirmed==2);++cases;}
 for(unsigned what=0;what<7;++what){Firmware f;if(what==0)f.noCapability=true;if(what==1)f.badTable=true;if(what==2)f.duplicateValue=true;if(what==3)f.rateUs=500001;if(what==4)f.irq=true;Config cfg={{3532800,4089600},true};if(what==5)cfg.capKhz[0]=0;if(what==6)cfg.capKhz[1]=4320000;CHECK(!initialize(&f.control,io(f),cfg,true)&&f.sets.empty());++cases;}
 {Firmware f;CHECK(start(f));f.rejectSet=1;firstSet(f);quiet(f);CHECK(f.control.phase==Stopped&&f.control.failure==Rejected&&f.sets.size()==1&&f.current[0]==8);++cases;}
 for(int status:{-7,-8,-9,-10,1}){Firmware f;CHECK(start(f));f.rejectSet=1;f.rejectStatus=status;firstSet(f);CHECK(f.control.phase==Held&&f.control.failure==FirmwareError&&f.control.dirty[0]);unsigned n=f.rings;stop(f);CHECK(f.rings==n&&!f.control.restoreConfirmed);++cases;}
 {Firmware f;CHECK(start(f));f.silentSet=1;firstSet(f);CHECK(f.control.phase==Held&&f.control.failure==Transport);unsigned rings=f.rings;quiet(f);stop(f);CHECK(f.rings==rings&&f.control.restoreConfirmed==0);++cases;}
 for(unsigned what=0;what<2;++what){Firmware f;CHECK(start(f));firstSet(f);if(what==0)f.rejectGet=true;else f.badGet=true;step(f,sample());CHECK(f.control.phase==Held&&f.control.failure==Readback&&f.sets.size()==1);unsigned rings=f.rings;stop(f);CHECK(f.rings==rings);++cases;}
 {Firmware f;CHECK(start(f));f.delayMs=2000;firstSet(f);quiet(f,60);CHECK(f.control.phase==Held&&f.control.failure==ConfirmationTimeout&&f.control.confirmations==0&&f.sets.size()==1);++cases;}
 {Firmware f;CHECK(start(f));firstSet(f);step(f,sample(),1100);CHECK(f.control.phase==Held&&f.current[0]<8&&f.control.confirmations==0&&f.sets.size()==1);++cases;}
 {Firmware f;CHECK(start(f));firstSet(f);stop(f);CHECK(f.control.phase==Stopped&&f.current[0]==8&&f.control.restoreConfirmed==1);++cases;}
 {Firmware f;CHECK(start(f));quiet(f);auto in=sample();in.ready=false;for(unsigned n=0;n<20&&!terminal(&f.control);++n)step(f,in);CHECK(f.control.phase==Stopped&&f.control.failure==ReadinessLost&&f.current[0]==8);++cases;}
 {Firmware f;CHECK(start(f));quiet(f);f.rejectSet=f.sets.size()+1;stop(f);CHECK(f.control.phase==Held&&f.control.restoreSets==1&&!f.control.restoreConfirmed);++cases;}
 {Firmware f;CHECK(start(f));quiet(f);auto in=sample();in.cpu[7].domain=0;step(f,in);stop(f);CHECK(f.control.failure==InvalidWindow&&f.control.phase==Stopped&&f.current[0]==8);++cases;}
 {Firmware f;CHECK(start(f));quiet(f);unsigned n=f.rings;f.ticks=0;elden_cpufreq::step(&f.control,sample());CHECK(f.control.phase==Held&&f.control.failure==Clock&&f.rings==n);++cases;}
 {Firmware f;f.rateUs=100000;CHECK(start(f));quiet(f);for(unsigned n=0;n<50;++n)step(f,sample(n%8<4?1000:0));stop(f);for(size_t n=1;n<f.sets.size();++n)CHECK(f.sets[n].at-f.sets[n-1].at>=1920000);CHECK(f.control.phase==Stopped);++cases;}
 {Firmware f;f.rateUs=500000;f.delayMs=980;CHECK(start(f));firstSet(f);stop(f);CHECK(f.control.phase==Stopped&&f.control.restoreConfirmed==1&&f.current[0]==8);++cases;}
 // Deterministic changing workloads with periodic touches: every emitted SET
 // is checked at the real SCMI doorbell, and both original levels must return.
 for(unsigned seed=1;seed<=128;++seed){Firmware f;CHECK(start(f));uint32_t rng=seed,touches=0;for(unsigned n=0;n<250;++n){rng=rng*1664525u+1013904223u;if((rng&31)==0)touches++;auto in=sample(0,touches);for(unsigned c=0;c<8;++c){rng=rng*1664525u+1013904223u;in.cpu[c].busy=(uint64_t)384000*(rng%1001)/1000;}step(f,in);CHECK(!terminal(&f.control));}stop(f);CHECK(f.control.phase==Stopped&&f.current[0]==8&&f.current[1]==0);++cases;}
 printf("PASS %u scenarios / %u checks: actual demand policy + SCMI transport + restore controller\n",cases,checks);
}
